package qa.qu.trakn.aptool.ui.map

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.wifi.WifiManager
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import qa.qu.trakn.aptool.data.SettingsRepository
import qa.qu.trakn.aptool.data.api.RetrofitClient
import qa.qu.trakn.aptool.data.models.AccessPoint
import qa.qu.trakn.aptool.data.models.ApGroupUpsertRequest
import qa.qu.trakn.aptool.data.models.GridPoint
import qa.qu.trakn.aptool.data.models.PostApRequest
import qa.qu.trakn.aptool.data.models.ScannedAp
import java.util.UUID

private const val TAG = "MapViewModel"

// Floor plan pixel dimensions and scale
const val FLOOR_PLAN_PX_W = 595f
const val FLOOR_PLAN_PX_H = 842f
const val SCALE_PX_PER_M  = 10f

data class MapUiState(
    val floorPlanUrl: String? = null,
    val floorPlanError: String? = null,
    val placedAps: List<AccessPoint> = emptyList(),
    // Tap-to-record flow
    val pendingTapM: Pair<Double, Double>? = null,   // (xm, ym) chosen by user tap
    val pendingBestAp: ScannedAp? = null,            // strongest AP at tap time
    val pendingGroup: List<ScannedAp> = emptyList(), // all BSSIDs from same physical AP (subnet)
    val showConfirmSheet: Boolean = false,
    // Grid overlay
    val gridPoints: List<GridPoint> = emptyList(),
    val gridScale: Float = SCALE_PX_PER_M,           // px per metre from server
    // Snackbar
    val snackbarMsg: String? = null,
    // 5-second RSSI capture progress (null = idle, 0f–1f = in progress)
    val capturingProgress: Float? = null,
)

class MapViewModel(
    private val context: Context,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(MapUiState())
    val state: StateFlow<MapUiState> = _state.asStateFlow()

    private val wifiManager =
        context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager

    // Per-BSSID readings collected during the 5s capture window
    private data class ApReading(val ssid: String, val frequencyMhz: Int, val readings: MutableList<Int> = mutableListOf())
    private val captureData = mutableMapOf<String, ApReading>()

    init {
        loadFloorPlanUrl()
        startApSync()
        loadGridPoints()
    }

    private fun loadFloorPlanUrl() {
        viewModelScope.launch {
            val settings = settingsRepo.settings.first()
            val fpid = settings.selectedFloorPlanId
            if (fpid.isEmpty()) {
                _state.update {
                    it.copy(
                        floorPlanUrl = null,
                        floorPlanError = "No floor plan selected.\nOpen Settings and choose a floor plan first.",
                    )
                }
                return@launch
            }
            try {
                val api = RetrofitClient.get(settings.apiBaseUrl)
                val response = api.getFloorPlanImage(fpid)
                when {
                    response.isSuccessful -> {
                        val url = "${settings.apiBaseUrl}/api/v1/floor-plans/$fpid/image"
                        _state.update { it.copy(floorPlanUrl = url, floorPlanError = null) }
                    }
                    response.code() == 404 -> {
                        _state.update {
                            it.copy(
                                floorPlanUrl = null,
                                floorPlanError = "No image for this floor plan.\nUpload one in the Web Mapping Tool first (Step 1).",
                            )
                        }
                    }
                    else -> {
                        _state.update {
                            it.copy(
                                floorPlanUrl = null,
                                floorPlanError = "Server error ${response.code()} — check backend.",
                            )
                        }
                    }
                }
            } catch (e: Exception) {
                val url = "${settings.apiBaseUrl}/api/v1/floor-plans/$fpid/image"
                _state.update {
                    it.copy(
                        floorPlanUrl = url,
                        floorPlanError = "Cannot reach backend: ${e.message}",
                    )
                }
                Log.w(TAG, "Floor plan probe failed: ${e.message}")
            }
        }
    }

    private fun loadGridPoints() {
        viewModelScope.launch {
            try {
                val settings = settingsRepo.settings.first()
                val fpid = settings.selectedFloorPlanId.ifEmpty { return@launch }
                val api = RetrofitClient.get(settings.apiBaseUrl)
                val response = api.getFloorPlanGrid(fpid, settings.apiKey)
                _state.update {
                    it.copy(
                        gridPoints = response.points,
                        gridScale = response.scalePxPerM.toFloat(),
                    )
                }
            } catch (e: Exception) {
                Log.w(TAG, "Grid points load failed: ${e.message}")
            }
        }
    }

    private fun startApSync() {
        viewModelScope.launch {
            while (true) {
                try {
                    val settings = settingsRepo.settings.first()
                    val fpid = settings.selectedFloorPlanId
                    if (fpid.isNotEmpty()) {
                        val api = RetrofitClient.get(settings.apiBaseUrl)
                        val response = api.getFloorPlanAps(fpid, settings.apiKey)
                        _state.update { it.copy(placedAps = response.accessPoints) }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "AP sync failed: ${e.message}")
                }
                delay(5_000)
            }
        }
    }

    /**
     * Group key for a BSSID.
     * Two BSSIDs belong to the same physical AP radio if:
     *   1. Their BSSID minus the last hex digit is identical, AND
     *   2. The last character of their last octet is the same class:
     *        - letter (a–f)  → one radio chain
     *        - digit  (0–9)  → another radio chain
     *
     * Example: 24:16:1b:76:27:2c and 24:16:1b:76:27:2d  → same group ("…:2:alpha")
     *          24:16:1b:76:27:20 and 24:16:1b:76:27:23  → same group ("…:2:digit")
     *          24:16:1b:76:27:2c vs 24:16:1b:76:27:8c   → DIFFERENT groups ("…:2:alpha" vs "…:8:alpha")
     */
    private fun macGroup(bssid: String): String {
        val normalized = bssid.lowercase().trimEnd()
        if (normalized.length < 2) return normalized
        // Group key = everything except the last hex digit.
        // e.g. "24:16:1b:76:28:cd" and "24:16:1b:76:28:c1" → "24:16:1b:76:28:c"
        // This correctly unifies the 2.4 GHz and 5 GHz BSSIDs of the same physical AP.
        return normalized.dropLast(1)
    }


    /**
     * Called when the user taps a location on the floor plan.
     * Starts a 5-second RSSI capture: scans every 500 ms, averages readings per BSSID,
     * then groups BSSIDs from the same physical AP and shows the confirm sheet.
     */
    fun onMapTap(xPx: Float, yPx: Float) {
        if (_state.value.capturingProgress != null) return   // already capturing
        val xm = (xPx / SCALE_PX_PER_M).toDouble()
        val ym = (yPx / SCALE_PX_PER_M).toDouble()
        viewModelScope.launch { capture(xm, ym) }
    }

    @SuppressLint("MissingPermission")
    private suspend fun capture(xm: Double, ym: Double) {
        captureData.clear()
        _state.update { it.copy(capturingProgress = 0f, pendingTapM = Pair(xm, ym)) }

        fun collectResults() {
            @Suppress("DEPRECATION")
            (wifiManager.scanResults ?: return).forEach { sr ->
                val bssid = sr.BSSID ?: return@forEach
                @Suppress("DEPRECATION") val ssid = sr.SSID ?: ""
                captureData.getOrPut(bssid) { ApReading(ssid, sr.frequency) }.readings.add(sr.level)
            }
        }

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) { collectResults() }
        }
        context.applicationContext.registerReceiver(
            receiver, IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION)
        )
        collectResults()   // seed with whatever is already cached

        val startMs = System.currentTimeMillis()
        val captureMs = 5_000L
        while (System.currentTimeMillis() - startMs < captureMs) {
            val elapsed  = System.currentTimeMillis() - startMs
            _state.update { it.copy(capturingProgress = (elapsed / captureMs.toFloat()).coerceIn(0f, 1f)) }
            @Suppress("DEPRECATION") wifiManager.startScan()
            delay(500)
        }

        try { context.applicationContext.unregisterReceiver(receiver) } catch (_: Exception) {}
        _state.update { it.copy(capturingProgress = null) }

        if (captureData.isEmpty()) {
            _state.update { it.copy(snackbarMsg = "No APs detected — try again") }
            return
        }

        // Average RSSI per BSSID and build ScannedAp list (all bands)
        val scanned = captureData.map { (bssid, r) ->
            ScannedAp(
                bssid        = bssid,
                ssid         = r.ssid,
                rssi         = r.readings.average().toInt(),
                rttSupported = false,
                frequencyMhz = r.frequencyMhz,
            )
        }.sortedByDescending { it.rssi }

        // Group all BSSIDs by physical AP (macGroup prefix), pick the group with
        // the highest average RSSI — more robust than relying on a single BSSID peak.
        val bestGroup = scanned
            .groupBy { macGroup(it.bssid) }
            .maxByOrNull { (_, aps) -> aps.map { it.rssi }.average() }
            ?.value ?: return

        if (bestGroup.isEmpty()) return
        val best = bestGroup.maxByOrNull { it.rssi } ?: return
        _state.update {
            it.copy(pendingBestAp = best, pendingGroup = bestGroup, showConfirmSheet = true)
        }
    }

    fun cancelPlacement() {
        _state.update {
            it.copy(
                showConfirmSheet = false,
                pendingTapM      = null,
                pendingBestAp    = null,
                pendingGroup     = emptyList(),
            )
        }
    }

    fun confirmPlacement() {
        val s     = _state.value
        val (xm, ym) = s.pendingTapM ?: return
        val group = s.pendingGroup.ifEmpty { listOfNotNull(s.pendingBestAp) }
        if (group.isEmpty()) return

        viewModelScope.launch {
            try {
                val settings = settingsRepo.settings.first()
                val fpid     = settings.selectedFloorPlanId
                if (fpid.isEmpty()) {
                    _state.update { it.copy(snackbarMsg = "No floor plan selected — open Settings first") }
                    return@launch
                }
                val api     = RetrofitClient.get(settings.apiBaseUrl)
                val groupId = UUID.randomUUID().toString()
                val newAps  = mutableListOf<AccessPoint>()

                api.postFloorPlanAps(
                    fpid,
                    settings.apiKey,
                    ApGroupUpsertRequest(
                        group.map { ap ->
                            PostApRequest(
                                bssid     = ap.bssid,
                                ssid      = ap.ssid,
                                rssiRef   = -38.0,
                                pathLossN = 2.1,
                                x         = xm,
                                y         = ym,
                                groupId   = groupId,
                            )
                        }
                    )
                )
                group.forEach { ap ->
                    newAps.add(AccessPoint(
                        bssid     = ap.bssid,
                        ssid      = ap.ssid,
                        rssiRef   = -38.0,
                        pathLossN = 2.1,
                        x         = xm,
                        y         = ym,
                    ))
                }

                val primary = group.first()
                val msg = if (group.size == 1) {
                    "Saved: ${primary.ssid} (${primary.bssid}) at (${String.format("%.1f", xm)}, ${String.format("%.1f", ym)}) m"
                } else {
                    "Saved ${group.size} BSSIDs for ${primary.ssid} at (${String.format("%.1f", xm)}, ${String.format("%.1f", ym)}) m"
                }

                _state.update {
                    it.copy(
                        placedAps        = (it.placedAps + newAps).distinctBy { a -> a.bssid },
                        showConfirmSheet = false,
                        pendingTapM      = null,
                        pendingBestAp    = null,
                        pendingGroup     = emptyList(),
                        snackbarMsg      = msg,
                    )
                }
            } catch (e: Exception) {
                _state.update { it.copy(snackbarMsg = "Save failed: ${e.message}") }
            }
        }
    }

    fun clearSnackbar() {
        _state.update { it.copy(snackbarMsg = null) }
    }
}
