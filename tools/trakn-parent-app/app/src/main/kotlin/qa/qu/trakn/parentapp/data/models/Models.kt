package qa.qu.trakn.parentapp.data.models

import com.google.gson.annotations.SerializedName

data class AccessPoint(
    val bssid: String = "",
    val ssid: String = "",
    @SerializedName("rssi_ref") val rssiRef: Double = -40.0,
    @SerializedName("path_loss_n") val pathLossN: Double = 2.7,
    val x: Double = 0.0,   // metres
    val y: Double = 0.0,   // metres
)

data class GetApsResponse(
    @SerializedName("access_points") val accessPoints: List<AccessPoint> = emptyList(),
)

data class HealthResponse(val status: String)

// A Wi-Fi AP visible in a scan — bssid + raw RSSI reading
data class ScannedAp(
    val bssid: String,
    val ssid: String,
    val rssi: Int,
)

// Output of the localization engine
data class LocationEstimate(
    val xM: Double,          // estimated x in metres
    val yM: Double,          // estimated y in metres
    val numAnchors: Int,     // how many APs contributed
    val avgErrorDb: Double,  // average |rssi_observed - rssi_model| in dB (quality indicator)
)

const val GATEWAY_API_KEY = "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990"

data class AppSettings(
    val apiBaseUrl: String = "https://35.238.189.188",
    val tagId: String      = "",   // TRAKN-XXXX; auto-fetched from server if blank
)

// Tag info returned by GET /api/v1/tags
data class TagInfo(
    @SerializedName("tag_id") val tagId: String,
    val mac: String,
    val name: String?,
)

data class TagsResponse(val tags: List<TagInfo> = emptyList())

// WebSocket position message from the backend
data class WsPosition(
    @SerializedName("tag_id")        val tagId: String = "",
    val x: Double                    = 0.0,
    val y: Double                    = 0.0,
    @SerializedName("heading_deg")   val headingDeg: Double = 0.0,
    @SerializedName("step_count")    val stepCount: Int = 0,
    val confidence: Double           = 0.0,
    val source: String               = "pdr_only",
    @SerializedName("bias_calibrated") val biasCalibrated: Boolean = false,
    @SerializedName("rssi_anchors")  val rssiAnchors: Int? = null,
    @SerializedName("rssi_error")    val rssiError: Double? = null,
    val ts: String                   = "",
)
