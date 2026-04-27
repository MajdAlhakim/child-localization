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
import qa.qu.trakn.parentapp.data.models.FloorPlanInfo
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

private const val RECONNECT_DELAY_MS   = 3_000L
private const val SCAN_INTERVAL_MS     = 2_000L
private const val TAG_POLL_INTERVAL_MS = 5_000L
private const val MIN_RSSI_DBM         = -85
private const val ALERT_DISTANCE_M     = 20.0
private const val ALERT_COOLDOWN_MS    = 60_000L
private const val NOTIF_CHANNEL_ID    = "trakn_alerts"
private const val NOTIF_ID             = 1001

data class LocateUiState(
    val floorPlanUrl: String?             = null,
    val floorPlanError: String?           = null,
    val knownAps: List<AccessPoint>       = emptyList(),
    val childEstimate: LocationEstimate?  = null,
    val parentEstimate: LocationEstimate? = null,
    val distanceM: Double?                = null,
    val alertActive: Boolean              = false,
    val statusMsg: String                 = "Connecting…",
    val wsConnected: Boolean              = false,
    val tagId: String                     = "",
    // Floor state
    val availableFloors: List<FloorPlanInfo> = emptyList(),
    val selectedFloorPlanId: String?      = null,
    val selectedFloorNumber: Int?         = null,
    val tagFloorNumber: Int?              = null,   // floor the tag is currently on
    val floorMenuOpen: Boolean            = false,
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
    private var trackingJob: Job?     = null

    // ── OkHttp client (trust-all SSL) ────────────────────────────────────────
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
            loadFloors()
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
        trackingJob?.cancel()
        trackingJob = viewModelScope.launch { startChildTracking() }
    }

    // ── Floor loading ─────────────────────────────────────────────────────────

    private suspend fun loadFloors() {
        val settings = settingsRepo.settings.first()
        try {
            val api    = RetrofitClient.get(settings.apiBaseUrl)
            val venues = api.getVenues().venues
            val floors = venues.firstOrNull()?.floorPlans
                ?.sortedBy { it.floorNumber }
                ?: emptyList()

            if (floors.isEmpty()) {
                _state.update {
                    it.copy(floorPlanError = "No floor plans found — upload via Web Mapping Tool.")
                }
                return
            }

            val firstFloor = floors.first()
            _state.update {
                it.copy(
                    availableFloors     = floors,
                    selectedFloorPlanId = firstFloor.id,
                    selectedFloorNumber = firstFloor.floorNumber,
                )
            }
            loadFloorPlanImage(firstFloor.id, settings.apiBaseUrl)
            loadKnownAps(firstFloor.id)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load floors: ${e.message}")
            _state.update {
                it.copy(floorPlanError = "Cannot reach backend: ${e.message}")
            }
        }
    }

    private suspend fun loadFloorPlanImage(fpId: String, baseUrl: String) {
        _state.update {
            it.copy(
                floorPlanUrl   = "$baseUrl/api/v1/floor-plans/$fpId/image",
                floorPlanError = null,
            )
        }
    }

    private suspend fun loadKnownAps(fpId: String) {
        try {
            val settings = settingsRepo.settings.first()
            val api      = RetrofitClient.get(settings.apiBaseUrl)
            val aps      = api.getFloorPlanAps(fpId, GATEWAY_API_KEY).accessPoints
            _state.update { it.copy(knownAps = aps) }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load APs for floor $fpId: ${e.message}")
        }
    }

    // ── Floor switching (parent manually changes the viewed floor) ────────────

    fun toggleFloorMenu() {
        _state.update { it.copy(floorMenuOpen = !it.floorMenuOpen) }
    }

    fun dismissFloorMenu() {
        _state.update { it.copy(floorMenuOpen = false) }
    }

    fun selectFloor(fp: FloorPlanInfo) {
        _state.update {
            it.copy(
                selectedFloorPlanId = fp.id,
                selectedFloorNumber = fp.floorNumber,
                floorMenuOpen       = false,
                knownAps            = emptyList(),
                childEstimate       = null,
                parentEstimate      = null,
                distanceM           = null,
            )
        }
        LocalizationEngine.resetHistory()
        viewModelScope.launch {
            val settings = settingsRepo.settings.first()
            loadFloorPlanImage(fp.id, settings.apiBaseUrl)
            loadKnownAps(fp.id)
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

        val filteredScan = rawScan.filter { it.rssi >= MIN_RSSI_DBM }

        val knownAps = _state.value.knownAps
        if (knownAps.isEmpty()) return

        val raw = LocalizationEngine.localize(filteredScan, knownAps) ?: return
        // LocalizationEngine already applies 3-zone adaptive EMA — no second pass needed.
        val parentEst = raw

        updateDistanceAndAlert(childEst = _state.value.childEstimate, parentEst = parentEst)
        _state.update { it.copy(parentEstimate = parentEst) }
    }

    // ── Child position — WebSocket ────────────────────────────────────────────

    private suspend fun startChildTracking() {
        val settings = settingsRepo.settings.first()
        val api      = RetrofitClient.get(settings.apiBaseUrl)

        var tagId = settings.tagId.trim()

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
                        if (!msg.biasCalibrated) return

                        val childEst = LocationEstimate(
                            xM         = msg.x,
                            yM         = msg.y,
                            numAnchors = msg.rssiAnchors ?: 0,
                            avgErrorDb = msg.rssiError   ?: 0.0,
                        )

                        val tagFloorFromMsg = msg.floorNumber
                        val tagFpId        = msg.floorPlanId
                        val cur            = _state.value

                        // Commit the tag's floor number immediately so the Canvas can gate
                        // rendering (tagOnThisFloor) independently of floor-switching logic.
                        _state.update { it.copy(tagFloorNumber = tagFloorFromMsg) }

                        // Auto-follow: switch the viewed floor to the tag's floor unless
                        // the parent has manually selected a different one.
                        // Include cur.tagFloorNumber == null so first-message always follows.
                        val autoFollow = cur.tagFloorNumber == null ||
                            cur.selectedFloorPlanId == null ||
                            cur.selectedFloorPlanId == cur.tagFloorPlanId() ||
                            cur.availableFloors.none { it.id == cur.selectedFloorPlanId }

                        if (autoFollow) {
                            // Prefer floor_plan_id; fall back to floor_number when id is null.
                            val targetFp = when {
                                tagFpId != null       -> cur.availableFloors.find { it.id == tagFpId }
                                tagFloorFromMsg != null -> cur.availableFloors.find { it.floorNumber == tagFloorFromMsg }
                                else                  -> null
                            }
                            if (targetFp != null && targetFp.id != cur.selectedFloorPlanId) {
                                _state.update {
                                    it.copy(
                                        selectedFloorPlanId = targetFp.id,
                                        selectedFloorNumber = targetFp.floorNumber,
                                        knownAps            = emptyList(),
                                    )
                                }
                                LocalizationEngine.resetHistory()
                                viewModelScope.launch {
                                    val settings = settingsRepo.settings.first()
                                    loadFloorPlanImage(targetFp.id, settings.apiBaseUrl)
                                    loadKnownAps(targetFp.id)
                                }
                            }
                        }

                        // Always store childEstimate — LocateScreen gates dot rendering via
                        // tagOnThisFloor. Only compute distance when on the same floor.
                        val sameFloor = tagFloorFromMsg == null ||
                            _state.value.selectedFloorNumber == null ||
                            tagFloorFromMsg == _state.value.selectedFloorNumber
                        if (sameFloor) {
                            updateDistanceAndAlert(childEst, _state.value.parentEstimate)
                        } else {
                            _state.update { it.copy(distanceM = null, alertActive = false) }
                        }
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
                        1000 -> { /* clean close */ }
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
        LocalizationEngine.resetHistory()
        _state.update {
            it.copy(
                childEstimate       = null,
                parentEstimate      = null,
                distanceM           = null,
                alertActive         = false,
                wsConnected         = false,
                statusMsg           = "Reconnecting…",
                availableFloors     = emptyList(),
                selectedFloorPlanId = null,
                selectedFloorNumber = null,
                tagFloorNumber      = null,
            )
        }
        viewModelScope.launch { loadFloors() }
        launchChildTracking()
    }
}

// Helper extension to get the floor plan ID that matches the tag's current floor
private fun LocateUiState.tagFloorPlanId(): String? =
    tagFloorNumber?.let { n -> availableFloors.find { it.floorNumber == n }?.id }
