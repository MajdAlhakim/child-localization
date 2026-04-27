package qa.qu.trakn.aptool.data.models

import com.google.gson.annotations.SerializedName

data class AccessPoint(
    val bssid: String = "",
    val ssid: String = "",
    @SerializedName("rssi_ref") val rssiRef: Double = -38.0,
    @SerializedName("path_loss_n") val pathLossN: Double = 2.1,
    val x: Double = 0.0,
    val y: Double = 0.0,
)

data class PostApRequest(
    val bssid: String,
    val ssid: String,
    @SerializedName("rssi_ref") val rssiRef: Double,
    @SerializedName("path_loss_n") val pathLossN: Double,
    val x: Double,
    val y: Double,
    @SerializedName("group_id") val groupId: String? = null,
)

data class GetApsResponse(
    @SerializedName("access_points") val accessPoints: List<AccessPoint> = emptyList(),
)

data class HealthResponse(val status: String)

data class GenericOkResponse(val status: String)

data class GridPoint(val x: Double, val y: Double)

data class GridPointsResponse(
    @SerializedName("scale_px_per_m") val scalePxPerM: Double = 10.0,
    @SerializedName("grid_spacing_m") val gridSpacingM: Double = 0.5,
    val points: List<GridPoint> = emptyList(),
)

// RTT measurement result
data class RttMeasurement(
    val distanceMm: Int,
    val stdDevMm: Int,
    val rssi: Int,
)

// Aggregated result from a 30-measurement session
data class RttSessionResult(
    val bssid: String,
    val ssid: String,
    val meanDistM: Double?,      // null if RTT not supported
    val stdDevM: Double?,        // null if RTT not supported
    val rssiRef: Double,
    val rttSupported: Boolean,
)

// Scan result wrapper (from WifiManager)
data class ScannedAp(
    val bssid: String,
    val ssid: String,
    val rssi: Int,
    val rttSupported: Boolean,
    val frequencyMhz: Int,
    val rttDistanceM: Double? = null,
    val rttStdDevM: Double? = null,
    val alreadyPlaced: Boolean = false,
)

// Venue / floor-plan discovery models
data class FloorPlanSummary(
    val id: String,
    @SerializedName("venue_id") val venueId: String,
    val name: String,
    @SerializedName("floor_number") val floorNumber: Int,
    @SerializedName("has_image") val hasImage: Boolean,
    @SerializedName("ap_count") val apCount: Int,
)

data class VenueSummary(
    val id: String,
    val name: String,
    val description: String,
    @SerializedName("floor_plans") val floorPlans: List<FloorPlanSummary>,
)

data class VenuesResponse(
    val venues: List<VenueSummary>,
)

// Batch AP upsert body — matches POST /api/v1/floor-plans/{fpid}/aps
data class ApGroupUpsertRequest(
    @SerializedName("access_points") val accessPoints: List<PostApRequest>,
)

// Settings
data class AppSettings(
    val apiBaseUrl: String = "https://35.238.189.188",
    val apiKey: String = "580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990",
    val rttMeasurementsPerSession: Int = 30,
    val rttMinDistM: Double = 0.8,
    val rttMaxDistM: Double = 1.2,
    // One-sided RTT offset: the AP "turn-around time" (SIFS ≈ 16 µs → ~2400 m) that must be
    // subtracted from raw one-sided RTT readings.  Typical range 2400–2700 m depending on AP model.
    // See Horn 2022 §8 — calibrate this value against a known distance for best accuracy.
    val oneSidedRttOffsetM: Double = 2500.0,
    // Active floor plan — empty string means none selected yet
    val selectedFloorPlanId: String = "",
    val selectedFloorPlanDisplay: String = "",  // e.g. "Building H07 — Floor 1"
)
