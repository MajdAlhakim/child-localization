package qa.qu.trakn.aptool.ui.scan

import android.annotation.SuppressLint
import android.content.Context
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.os.Build
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import qa.qu.trakn.aptool.data.SettingsRepository
import qa.qu.trakn.aptool.data.api.RetrofitClient
import qa.qu.trakn.aptool.data.models.ScannedAp

data class ScanUiState(
    val aps: List<ScannedAp> = emptyList(),
    val isScanning: Boolean = false,
)

class ScanViewModel(
    private val context: Context,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ScanUiState())
    val state: StateFlow<ScanUiState> = _state.asStateFlow()

    private val wifiManager: WifiManager by lazy {
        context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    }
    private var scanJob: Job? = null
    private var apSyncJob: Job? = null
    private var placedBssids = mutableSetOf<String>()
    private val stableApOrder = mutableListOf<String>()

    // Rolling RSSI history per BSSID — averaged before saving as rssiRef.
    // 5-scan window at 15 s interval = ~75 s of smoothing, eliminating single-scan spikes.
    private val rssiHistory = mutableMapOf<String, ArrayDeque<Int>>()
    private val RSSI_HISTORY_SIZE = 5

    /** The AP with the highest RSSI among currently visible APs. */
    val bestAp: ScannedAp? get() = _state.value.aps.maxByOrNull { it.rssi }

    init {
        startScanning()
        startApSync()
    }

    fun startScanning() {
        if (scanJob?.isActive == true) return
        _state.update { it.copy(isScanning = true) }
        scanJob = viewModelScope.launch {
            while (true) {
                refreshScan()
                delay(15_000)
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun refreshScan() {
        try {
            wifiManager.startScan()
            val results: List<ScanResult> = wifiManager.scanResults ?: emptyList()

            val currentAps = _state.value.aps
            val scanMap = HashMap<String, ScannedAp>(results.size)
            for (sr in results) {
                val rttSupported = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    sr.capabilities.contains("IEEE80211mc") ||
                    (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && sr.is80211mcResponder)
                } else false
                val existing = currentAps.find { ap -> ap.bssid == sr.BSSID }
                val q = rssiHistory.getOrPut(sr.BSSID) { ArrayDeque() }
                q.addLast(sr.level)
                if (q.size > RSSI_HISTORY_SIZE) q.removeFirst()
                val avgRssi = q.average().toInt()
                scanMap[sr.BSSID] = ScannedAp(
                    bssid = sr.BSSID,
                    ssid = sr.SSID.ifBlank { "<Hidden>" },
                    rssi = avgRssi,
                    rttSupported = rttSupported,
                    frequencyMhz = sr.frequency,
                    rttDistanceM = existing?.rttDistanceM,
                    rttStdDevM = existing?.rttStdDevM,
                    alreadyPlaced = placedBssids.contains(sr.BSSID),
                )
            }

            val newBssids = scanMap.keys
                .filter { bssid -> bssid !in stableApOrder }
                .sortedByDescending { bssid -> scanMap[bssid]?.rssi ?: -100 }
            stableApOrder.addAll(newBssids)
            stableApOrder.retainAll(scanMap.keys)

            val scanned = stableApOrder.mapNotNull { bssid -> scanMap[bssid] }
            _state.update { s -> s.copy(aps = scanned) }
        } catch (e: Exception) {
            // Ignore scan failures
        }
    }

    private fun startApSync() {
        apSyncJob = viewModelScope.launch {
            while (true) {
                try {
                    val settings = settingsRepo.settings.first()
                    val fpid = settings.selectedFloorPlanId
                    if (fpid.isEmpty()) { delay(10_000); continue }
                    val api = RetrofitClient.get(settings.apiBaseUrl)
                    val response = api.getFloorPlanAps(fpid, settings.apiKey)
                    placedBssids = response.accessPoints.map { it.bssid }.toMutableSet()
                    _state.update { s ->
                        s.copy(aps = s.aps.map { ap ->
                            ap.copy(alreadyPlaced = placedBssids.contains(ap.bssid))
                        })
                    }
                } catch (_: Exception) {}
                delay(10_000)
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        scanJob?.cancel()
        apSyncJob?.cancel()
    }
}
