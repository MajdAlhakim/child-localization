package qa.qu.trakn.aptool.ui.map

import android.content.Context
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
)

class MapViewModel(
    private val context: Context,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(MapUiState())
    val state: StateFlow<MapUiState> = _state.asStateFlow()

    init {
        loadFloorPlanUrl()
        startApSync()
        loadGridPoints()
    }

    private fun loadFloorPlanUrl() {
        viewModelScope.launch {
            val settings = settingsRepo.settings.first()
            try {
                val api = RetrofitClient.get(settings.apiBaseUrl)
                val response = api.getFloorPlan()
                when {
                    response.isSuccessful -> {
                        // Floor plan exists — hand the URL to Coil (which uses the SSL-trusted client)
                        val url = "${settings.apiBaseUrl}/api/v1/venue/floor-plan"
                        _state.update { it.copy(floorPlanUrl = url, floorPlanError = null) }
                    }
                    response.code() == 404 -> {
                        _state.update {
                            it.copy(
                                floorPlanUrl = null,
                                floorPlanError = "No floor plan on server.\nUpload one in the Web Mapping Tool first (Step 1).",
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
                // Network / SSL error — still try; Coil will show its own error state
                val url = "${settings.apiBaseUrl}/api/v1/venue/floor-plan"
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
                val api = RetrofitClient.get(settings.apiBaseUrl)
                val response = api.getGridPoints(settings.apiKey)
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
                    val api = RetrofitClient.get(settings.apiBaseUrl)
                    val response = api.getAps(settings.apiKey)
                    _state.update { it.copy(placedAps = response.accessPoints) }
                } catch (e: Exception) {
                    Log.w(TAG, "AP sync failed: ${e.message}")
                }
                delay(5_000)
            }
        }
    }

    /** Returns the first 5 octets of a BSSID (the subnet prefix for the physical AP). */
    private fun macPrefix(bssid: String): String =
        bssid.split(":").take(5).joinToString(":")

    /**
     * Called when the user taps a location on the floor plan.
     * [currentBestAp] is the strongest visible AP.
     * [allAps] is the full current scan list — used to find every BSSID sharing the same
     * physical AP (identical first 5 MAC octets = same subnet).
     */
    fun onMapTap(xPx: Float, yPx: Float, currentBestAp: ScannedAp?, allAps: List<ScannedAp>) {
        val xm = xPx / SCALE_PX_PER_M
        val ym = yPx / SCALE_PX_PER_M
        if (currentBestAp == null) {
            _state.update { it.copy(snackbarMsg = "No APs visible — wait for scan to complete") }
            return
        }
        val prefix = macPrefix(currentBestAp.bssid)
        val group  = allAps.filter { macPrefix(it.bssid) == prefix }
                           .sortedByDescending { it.rssi }
                           .ifEmpty { listOf(currentBestAp) }
        _state.update {
            it.copy(
                pendingTapM    = Pair(xm.toDouble(), ym.toDouble()),
                pendingBestAp  = currentBestAp,
                pendingGroup   = group,
                showConfirmSheet = true,
            )
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
                val api      = RetrofitClient.get(settings.apiBaseUrl)
                // All BSSIDs from the same physical AP share one group_id
                val groupId  = UUID.randomUUID().toString()
                val newAps   = mutableListOf<AccessPoint>()

                for (ap in group) {
                    api.postAp(
                        settings.apiKey,
                        PostApRequest(
                            bssid     = ap.bssid,
                            ssid      = ap.ssid,
                            rssiRef   = ap.rssi.toDouble(),
                            pathLossN = 2.7,
                            x         = xm,
                            y         = ym,
                            groupId   = groupId,
                        )
                    )
                    newAps.add(AccessPoint(
                        bssid     = ap.bssid,
                        ssid      = ap.ssid,
                        rssiRef   = ap.rssi.toDouble(),
                        pathLossN = 2.7,
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
