package qa.qu.trakn.aptool.ui.settings

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import qa.qu.trakn.aptool.data.SettingsRepository
import qa.qu.trakn.aptool.data.api.RetrofitClient
import qa.qu.trakn.aptool.data.models.AppSettings

data class SettingsUiState(
    val settings: AppSettings = AppSettings(),
    val testResult: String? = null,
    val isTesting: Boolean = false,
)

class SettingsViewModel(
    private val context: Context,
    private val settingsRepo: SettingsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(SettingsUiState())
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val s = settingsRepo.settings.first()
            _state.update { it.copy(settings = s) }
        }
    }

    fun updateBaseUrl(v: String) { _state.update { it.copy(settings = it.settings.copy(apiBaseUrl = v)) } }
    fun updateApiKey(v: String) { _state.update { it.copy(settings = it.settings.copy(apiKey = v)) } }
    fun updateRttCount(v: Int) { _state.update { it.copy(settings = it.settings.copy(rttMeasurementsPerSession = v)) } }
    fun updateRttMin(v: Double) { _state.update { it.copy(settings = it.settings.copy(rttMinDistM = v)) } }
    fun updateRttMax(v: Double) { _state.update { it.copy(settings = it.settings.copy(rttMaxDistM = v)) } }
    fun updateOneSidedOffset(v: Double) { _state.update { it.copy(settings = it.settings.copy(oneSidedRttOffsetM = v)) } }

    fun save() {
        viewModelScope.launch {
            settingsRepo.update(_state.value.settings)
        }
    }

    fun testConnection() {
        viewModelScope.launch {
            _state.update { it.copy(isTesting = true, testResult = null) }
            try {
                val s = _state.value.settings
                val api = RetrofitClient.get(s.apiBaseUrl)
                val health = api.health()
                _state.update { it.copy(testResult = "✓ ${health.status}", isTesting = false) }
            } catch (e: Exception) {
                _state.update { it.copy(testResult = "✗ ${e.message}", isTesting = false) }
            }
        }
    }
}
