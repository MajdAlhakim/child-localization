package qa.qu.trakn.parentapp.ui.locate

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.wifi.WifiManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.gson.Gson
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import qa.qu.trakn.parentapp.data.SettingsRepository
import qa.qu.trakn.parentapp.data.models.GATEWAY_API_KEY
import qa.qu.trakn.parentapp.data.api.RetrofitClient
import qa.qu.trakn.parentapp.data.models.AccessPoint
import qa.qu.trakn.parentapp.data.models.LocationEstimate
import qa.qu.trakn.parentapp.data.models.ScannedAp
import qa.qu.trakn.parentapp.data.models.WsPosition
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager
import kotlin.math.sqrt

private const val TAG = "LocateViewModel"
const val SCALE_PX_PER_M = 10f

private const val RECONNECT_DELAY_MS  = 3_000L
private const val SCAN_INTERVAL_MS    = 2_000L
private const val TAG_POLL_INTERVAL_MS = 5_000L
private const val RSSI_ALPHA          = 0.25
private const val POS_ALPHA           = 0.25
private const val MIN_RSSI_DBM        = -85
private const val ALERT_DISTANCE_M    = 20.0
private const val ALERT_COOLDOWN_MS   = 60_000L
private const val NOTIF_CHANNEL_ID   = "trakn_alerts"
private const val NOTIF_ID            = 1001

data class LocateUiState(
    val floorPlanUrl: String?             = null,
    val floorPlanError: String?           = null,
    val knownAps: List<AccessPoint>       = emptyList(),
    val childEstimate: LocationEstimate?  = null,   // child tag — from WebSocket
    val parentEstimate: LocationEstimate? = null,   // parent phone — from local Wi-Fi scan
    val distanceM: Double?                = null,   // metres between child and parent
    val alertActive: Boolean              = false,  // true when distance > ALERT_DISTANCE_M
    val statusMsg: String                 = "Connecting…",
    val wsConnected: Boolean              = false,
    val tagId: String                     = "",
)

class LocateViewModel(
    private val context: Context,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(LocateUiState())
    val state: StateFlow<LocateUiState> = _state.asStateFlow()

    private val gson = Gson()
    private var webSocket: WebSocket? = null
    private var activeWsUrl: String   = ""
    private var lastAlertMs: Long     = 0L
    private var trackingJob: Job?     = null   // guards against concurrent startChildTracking() loops

    // ── OkHttp client (trust-all SSL, same self-signed cert) ─────────────────
    private val trustAll = arrayOf<TrustManager>(object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    })
    private val wsClient: OkHttpClient = run {
        val ssl = SSLContext.getInstance("TLS").apply { init(null, trustAll, SecureRandom()) }
        OkHttpClient.Builder()
            .sslSocketFactory(ssl.socketFactory, trustAll[0] as X509TrustManager)
            .hostnameVerifier { _, _ -> true }
            .build()
    }

    // ── Local Wi-Fi scan (parent position) ───────────────────────────────────
    private val wifiManager =
        context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val smoothedRssi = mutableMapOf<String, Double>()
    private var smoothedX: Double? = null
    private var smoothedY: Double? = null

    private val scanReceiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            processParentScan()
        }
    }

    init {
        createNotificationChannel()
        context.applicationContext.registerReceiver(
            scanReceiver,
            IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION),
        )
        viewModelScope.launch {
            loadFloorPlan()
            loadKnownAps()
            processParentScan()
            launch { scanLoop() }
        }
    }

    fun startTracking() {
        launchChildTracking()
    }

    override fun onCleared() {
        super.onCleared()
        try { context.applicationContext.unregisterReceiver(scanReceiver) } catch (_: Exception) {}
        trackingJob?.cancel()
        webSocket?.close(1000, "ViewModel cleared")
        webSocket = null
    }

    private fun launchChildTracking() {
        trackingJob?.cancel()   // kill any previous poll loop before starting a new one
        trackingJob = viewModelScope.launch { startChildTracking() }
    }

    // ── Data loading ─────────────────────────────────────────────────────────

    private suspend fun loadFloorPlan() {
        val settings = settingsRepo.settings.first()
        try {
            val api = RetrofitClient.get(settings.apiBaseUrl)
            if (api.getFloorPlan().isSuccessful) {
                _state.update {
                    it.copy(
                        floorPlanUrl   = "${settings.apiBaseUrl}/api/v1/venue/floor-plan",
                        floorPlanError = null,
                    )
                }
            } else {
                _state.update {
                    it.copy(floorPlanUrl = null,
                        floorPlanError = "No floor plan — upload via Web Mapping Tool.")
                }
            }
        } catch (e: Exception) {
            _state.update {
                it.copy(
                    floorPlanUrl   = "${settings.apiBaseUrl}/api/v1/venue/floor-plan",
                    floorPlanError = "Cannot reach backend: ${e.message}",
                )
            }
        }
    }

    private suspend fun loadKnownAps() {
        try {
            val settings = settingsRepo.settings.first()
            val api      = RetrofitClient.get(settings.apiBaseUrl)
            val aps      = api.getAps(GATEWAY_API_KEY).accessPoints
            _state.update { it.copy(knownAps = aps) }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load APs: ${e.message}")
        }
    }

    // ── Parent position — local Wi-Fi scan ───────────────────────────────────

    private suspend fun scanLoop() {
        while (true) {
            @Suppress("DEPRECATION")
            wifiManager.startScan()
            delay(SCAN_INTERVAL_MS)
        }
    }

    @Suppress("DEPRECATION")
    private fun processParentScan() {
        val results  = wifiManager.scanResults ?: emptyList()
        val rawScan  = results.mapNotNull { r ->
            if (r.BSSID.isNullOrEmpty()) null
            else ScannedAp(bssid = r.BSSID, ssid = r.SSID ?: "", rssi = r.level)
        }

        val activeBssids = rawScan.map { it.bssid.lowercase() }.toSet()
        smoothedRssi.keys.retainAll(activeBssids)

        val smoothedScan = rawScan.map { ap ->
            val key  = ap.bssid.lowercase()
            val prev = smoothedRssi[key] ?: ap.rssi.toDouble()
            val next = RSSI_ALPHA * ap.rssi + (1.0 - RSSI_ALPHA) * prev
            smoothedRssi[key] = next
            ap.copy(rssi = next.toInt())
        }.filter { it.rssi >= MIN_RSSI_DBM }

        val knownAps = _state.value.knownAps
        if (knownAps.isEmpty()) return

        val raw = LocalizationEngine.localize(smoothedScan, knownAps) ?: return

        val sx = smoothedX; val sy = smoothedY
        if (sx == null || sy == null) {
            smoothedX = raw.xM; smoothedY = raw.yM
        } else {
            smoothedX = POS_ALPHA * raw.xM + (1.0 - POS_ALPHA) * sx
            smoothedY = POS_ALPHA * raw.yM + (1.0 - POS_ALPHA) * sy
        }
        val parentEst = raw.copy(xM = smoothedX!!, yM = smoothedY!!)

        updateDistanceAndAlert(childEst = _state.value.childEstimate, parentEst = parentEst)
        _state.update { it.copy(parentEstimate = parentEst) }
    }

    // ── Child position — WebSocket ────────────────────────────────────────────

    private suspend fun startChildTracking() {
        val settings = settingsRepo.settings.first()
        val api      = RetrofitClient.get(settings.apiBaseUrl)

        var tagId = settings.tagId.trim()

        // If no tag ID is configured, poll the server until one registers.
        // The tag must send at least one packet before it appears in /api/v1/tags.
        if (tagId.isBlank()) {
            while (tagId.isBlank()) {
                try {
                    val tags = api.getTags(GATEWAY_API_KEY).tags
                    tagId = tags.firstOrNull()?.tagId ?: ""
                    if (tagId.isBlank()) {
                        _state.update {
                            it.copy(statusMsg = "Tag not registered yet (0 tags on server).\nIs the tag powered on and sending packets?\nOr enter Tag ID manually in Settings.")
                        }
                    }
                } catch (e: retrofit2.HttpException) {
                    val msg = when (e.code()) {
                        401  -> "Wrong API key — check Settings."
                        404  -> "Tags endpoint not found — check server URL."
                        else -> "Server error ${e.code()} fetching tags."
                    }
                    _state.update { it.copy(statusMsg = msg) }
                    Log.w(TAG, "getTags HTTP ${e.code()}: ${e.message()}")
                } catch (e: Exception) {
                    _state.update {
                        it.copy(statusMsg = "Cannot reach server: ${e.message}\nCheck URL in Settings.")
                    }
                    Log.w(TAG, "getTags failed: ${e.message}")
                }
                if (tagId.isBlank()) delay(TAG_POLL_INTERVAL_MS)
            }
        }

        _state.update { it.copy(tagId = tagId) }

        val wsBase = settings.apiBaseUrl
            .replace("https://", "wss://")
            .replace("http://", "ws://")
            .trimEnd('/')
        connectWebSocket("$wsBase/ws/position/$tagId")
    }

    private fun connectWebSocket(wsUrl: String) {
        if (wsUrl == activeWsUrl && webSocket != null) return
        webSocket?.close(1000, "Reconnecting")
        webSocket   = null
        activeWsUrl = wsUrl

        _state.update { it.copy(wsConnected = false, statusMsg = "Connecting…") }

        webSocket = wsClient.newWebSocket(
            Request.Builder().url(wsUrl).build(),
            object : WebSocketListener() {

                override fun onOpen(webSocket: WebSocket, response: Response) {
                    _state.update { it.copy(wsConnected = true, statusMsg = "Tracking") }
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    try {
                        val msg = gson.fromJson(text, WsPosition::class.java)
                        if (!msg.biasCalibrated) return   // skip until IMU is ready

                        val childEst = LocationEstimate(
                            xM         = msg.x,
                            yM         = msg.y,
                            numAnchors = msg.rssiAnchors ?: 0,
                            avgErrorDb = msg.rssiError   ?: 0.0,
                        )
                        updateDistanceAndAlert(childEst, _state.value.parentEstimate)
                        _state.update {
                            it.copy(childEstimate = childEst, wsConnected = true, statusMsg = "Tracking")
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "WS parse error: ${e.message}")
                    }
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    _state.update { it.copy(wsConnected = false, statusMsg = "Reconnecting…") }
                    scheduleReconnect(wsUrl)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    when (code) {
                        1000 -> { /* clean close — do nothing */ }
                        4004 -> {
                            _state.update {
                                it.copy(wsConnected = false,
                                    statusMsg = "Tag not registered yet.\nWaiting for tag to come online…")
                            }
                            scheduleReconnect(wsUrl, delayMs = 10_000L)
                        }
                        else -> {
                            _state.update { it.copy(wsConnected = false, statusMsg = "Reconnecting…") }
                            scheduleReconnect(wsUrl)
                        }
                    }
                }
            }
        )
    }

    private fun scheduleReconnect(wsUrl: String, delayMs: Long = RECONNECT_DELAY_MS) {
        viewModelScope.launch {
            delay(delayMs)
            activeWsUrl = ""
            connectWebSocket(wsUrl)
        }
    }

    // ── Distance + alert ─────────────────────────────────────────────────────

    private fun updateDistanceAndAlert(
        childEst: LocationEstimate?,
        parentEst: LocationEstimate?,
    ) {
        if (childEst == null || parentEst == null) {
            _state.update { it.copy(distanceM = null, alertActive = false) }
            return
        }
        val dx   = childEst.xM - parentEst.xM
        val dy   = childEst.yM - parentEst.yM
        val dist = sqrt(dx * dx + dy * dy)
        val alert = dist > ALERT_DISTANCE_M

        _state.update { it.copy(distanceM = dist, alertActive = alert) }

        if (alert) maybeNotify(dist)
    }

    private fun maybeNotify(distanceM: Double) {
        val now = System.currentTimeMillis()
        if (now - lastAlertMs < ALERT_COOLDOWN_MS) return
        lastAlertMs = now

        val canNotify = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

        if (!canNotify) return

        val notification = NotificationCompat.Builder(context, NOTIF_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Child is far away!")
            .setContentText("Your child is ${distanceM.toInt()} m away from you.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()

        NotificationManagerCompat.from(context).notify(NOTIF_ID, notification)
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            NOTIF_CHANNEL_ID,
            "Child Distance Alerts",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Notifies when your child moves beyond $ALERT_DISTANCE_M m"
        }
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .createNotificationChannel(channel)
    }

    // ── Manual refresh ────────────────────────────────────────────────────────

    fun refresh() {
        webSocket?.close(1000, "Manual refresh")
        webSocket   = null
        activeWsUrl = ""
        smoothedRssi.clear()
        smoothedX = null
        smoothedY = null
        _state.update {
            it.copy(
                childEstimate  = null,
                parentEstimate = null,
                distanceM      = null,
                alertActive    = false,
                wsConnected    = false,
                statusMsg      = "Reconnecting…",
            )
        }
        viewModelScope.launch {
            loadFloorPlan()
            loadKnownAps()
        }
        launchChildTracking()   // cancels any existing poll loop, starts exactly one new one
    }
}
