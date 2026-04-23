package qa.qu.trakn.aptool.data

import android.content.Context
import androidx.datastore.preferences.core.doublePreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import qa.qu.trakn.aptool.data.models.AppSettings

val Context.dataStore by preferencesDataStore(name = "trakn_settings")

class SettingsRepository(private val context: Context) {

    companion object {
        val KEY_BASE_URL          = stringPreferencesKey("base_url")
        val KEY_API_KEY           = stringPreferencesKey("api_key")
        val KEY_RTT_COUNT         = intPreferencesKey("rtt_count")
        val KEY_RTT_MIN           = doublePreferencesKey("rtt_min")
        val KEY_RTT_MAX           = doublePreferencesKey("rtt_max")
        val KEY_ONE_SIDED_OFFSET  = doublePreferencesKey("one_sided_offset")
        val KEY_FLOOR_PLAN_ID     = stringPreferencesKey("floor_plan_id")
        val KEY_FLOOR_PLAN_DISPLAY = stringPreferencesKey("floor_plan_display")
    }

    val settings: Flow<AppSettings> = context.dataStore.data.map { prefs ->
        AppSettings(
            apiBaseUrl                = prefs[KEY_BASE_URL] ?: "https://35.238.189.188",
            apiKey                    = prefs[KEY_API_KEY] ?: "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990",
            rttMeasurementsPerSession = prefs[KEY_RTT_COUNT] ?: 30,
            rttMinDistM               = prefs[KEY_RTT_MIN] ?: 0.8,
            rttMaxDistM               = prefs[KEY_RTT_MAX] ?: 1.2,
            oneSidedRttOffsetM        = prefs[KEY_ONE_SIDED_OFFSET] ?: 2500.0,
            selectedFloorPlanId       = prefs[KEY_FLOOR_PLAN_ID] ?: "",
            selectedFloorPlanDisplay  = prefs[KEY_FLOOR_PLAN_DISPLAY] ?: "",
        )
    }

    suspend fun update(settings: AppSettings) {
        context.dataStore.edit { prefs ->
            prefs[KEY_BASE_URL]           = settings.apiBaseUrl
            prefs[KEY_API_KEY]            = settings.apiKey
            prefs[KEY_RTT_COUNT]          = settings.rttMeasurementsPerSession
            prefs[KEY_RTT_MIN]            = settings.rttMinDistM
            prefs[KEY_RTT_MAX]            = settings.rttMaxDistM
            prefs[KEY_ONE_SIDED_OFFSET]   = settings.oneSidedRttOffsetM
            prefs[KEY_FLOOR_PLAN_ID]      = settings.selectedFloorPlanId
            prefs[KEY_FLOOR_PLAN_DISPLAY] = settings.selectedFloorPlanDisplay
        }
    }
}
