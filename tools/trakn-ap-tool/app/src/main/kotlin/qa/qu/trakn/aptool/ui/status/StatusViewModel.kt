package qa.qu.trakn.aptool.ui.status

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

data class StatusUiState(
    val aps: List<AccessPoint> = emptyList(),
    val backendConnected: Boolean = false,
    val lastSuccessMs: Long = 0L,
    val showDeleteConfirm: Boolean = false,
    val isDeleting: Boolean = false,
    val snackbarMsg: String? = null,
)

private const val TAG = "StatusViewModel"

class StatusViewModel(
    private val context: Context,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(StatusUiState())
    val state: StateFlow<StatusUiState> = _state.asStateFlow()

    init {
        startPolling()
    }

    private fun startPolling() {
        viewModelScope.launch {
            while (true) {
                fetchAps()
                delay(5_000)
            }
        }
    }

    private suspend fun fetchAps() {
        try {
            val settings = settingsRepo.settings.first()
            val fpid = settings.selectedFloorPlanId.ifEmpty { return }
            val api = RetrofitClient.get(settings.apiBaseUrl)
            val resp = api.getFloorPlanAps(fpid, settings.apiKey)
            _state.update {
                it.copy(aps = resp.accessPoints, backendConnected = true, lastSuccessMs = System.currentTimeMillis())
            }
        } catch (e: Exception) {
            val elapsed = System.currentTimeMillis() - _state.value.lastSuccessMs
            _state.update { it.copy(backendConnected = elapsed < 10_000) }
            Log.w(TAG, "Fetch APs failed: ${e.message}")
        }
    }

    fun requestDeleteAll() {
        _state.update { it.copy(showDeleteConfirm = true) }
    }

    fun dismissDeleteConfirm() {
        _state.update { it.copy(showDeleteConfirm = false) }
    }

    fun confirmDeleteAll() {
        viewModelScope.launch {
            _state.update { it.copy(isDeleting = true, showDeleteConfirm = false) }
            try {
                val settings = settingsRepo.settings.first()
                val fpid = settings.selectedFloorPlanId.ifEmpty {
                    _state.update { it.copy(snackbarMsg = "No floor plan selected", isDeleting = false) }
                    return@launch
                }
                val api = RetrofitClient.get(settings.apiBaseUrl)
                api.deleteFloorPlanAps(fpid, settings.apiKey)
                _state.update { it.copy(aps = emptyList(), snackbarMsg = "All APs cleared", isDeleting = false) }
            } catch (e: Exception) {
                _state.update { it.copy(snackbarMsg = "Delete failed: ${e.message}", isDeleting = false) }
            }
        }
    }

    fun clearSnackbar() {
        _state.update { it.copy(snackbarMsg = null) }
    }
}
