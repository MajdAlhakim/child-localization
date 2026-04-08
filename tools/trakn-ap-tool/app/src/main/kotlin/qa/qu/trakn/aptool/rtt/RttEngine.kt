package qa.qu.trakn.aptool.rtt

import android.annotation.SuppressLint
import android.content.Context
import android.net.wifi.ScanResult
import android.net.wifi.rtt.RangingRequest
import android.net.wifi.rtt.RangingResult
import android.net.wifi.rtt.RangingResultCallback
import android.net.wifi.rtt.WifiRttManager
import android.util.Log
import qa.qu.trakn.aptool.data.models.RttMeasurement
import java.util.concurrent.Executor
import kotlin.math.max
import kotlin.math.sqrt

private const val TAG = "RttEngine"

class RttEngine(context: Context) {

    private val wifiRttManager: WifiRttManager? =
        context.getSystemService(Context.WIFI_RTT_RANGING_SERVICE) as? WifiRttManager
    private val mainExecutor: Executor = context.mainExecutor

    val isAvailable: Boolean get() = wifiRttManager?.isAvailable == true

    /**
     * One-sided RTT measurement using [RangingRequest.Builder.addNon80211mcCapableAccessPoint].
     * This works with ANY Wi-Fi AP — the AP only needs to send a normal ACK (no IEEE 802.11mc
     * cooperation required).  The raw distanceMm returned by Android includes the AP "turn-around"
     * time (~16 µs SIFS → ~2400–2700 m).  The caller is responsible for subtracting the
     * per-AP-model offset before using the value as a physical distance estimate.
     * See: Horn 2022, "Indoor Localization Using Uncooperative Wi-Fi Access Points", §3 & §8.
     */
    @SuppressLint("MissingPermission")
    fun measureRtt(
        scanResult: ScanResult,
        callback: (rawDistanceMm: Int, stdDevMm: Int, rssi: Int) -> Unit,
    ) {
        val mgr = wifiRttManager ?: run {
            Log.w(TAG, "WifiRttManager not available")
            return
        }
        if (!mgr.isAvailable) {
            Log.w(TAG, "RTT not available on this device")
            return
        }

        // Use addNon80211mcCapableAccessPoint so any AP — including legacy ones that don't
        // advertise IEEE 802.11mc — can be ranged via one-sided FTM RTT.
        val request = RangingRequest.Builder()
            .addNon80211mcCapableAccessPoint(scanResult)
            .build()

        mgr.startRanging(request, mainExecutor, object : RangingResultCallback() {
            override fun onRangingFailure(code: Int) {
                Log.w(TAG, "Ranging failure code=$code")
            }

            override fun onRangingResults(results: List<RangingResult>) {
                val r = results.firstOrNull() ?: return
                if (r.status == RangingResult.STATUS_SUCCESS) {
                    callback(r.distanceMm, r.distanceStdDevMm, r.rssi)
                } else {
                    Log.w(TAG, "Ranging result not successful: status=${r.status}")
                }
            }
        })
    }

    /**
     * Runs [targetCount] one-sided RTT measurements against [scanResult].
     * [oneSidedOffsetMm] is the AP turn-around bias (in mm) to subtract from each raw reading.
     * Emits progress after each measurement; the stored [RttMeasurement.distanceMm] is already
     * offset-corrected and floored at 0.
     */
    @SuppressLint("MissingPermission")
    fun runSession(
        scanResult: ScanResult,
        targetCount: Int,
        oneSidedOffsetMm: Int,
        onProgress: (measurements: List<RttMeasurement>, done: Boolean) -> Unit,
    ) {
        val measurements = mutableListOf<RttMeasurement>()
        var completed = false

        fun tryNext() {
            if (completed || measurements.size >= targetCount) return
            measureRtt(scanResult) { rawMm, stdDevMm, rssi ->
                // Subtract the one-sided RTT offset (AP turn-around / SIFS bias).
                val correctedMm = max(0, rawMm - oneSidedOffsetMm)
                measurements.add(RttMeasurement(correctedMm, stdDevMm, rssi))
                val done = measurements.size >= targetCount
                if (done) completed = true
                onProgress(measurements.toList(), done)
                if (!done) {
                    mainExecutor.execute { tryNext() }
                }
            }
        }
        tryNext()
    }

    companion object {
        fun computeSessionStats(
            measurements: List<RttMeasurement>,
            minDistM: Double,
            maxDistM: Double,
        ): Triple<Double, Double, Double> {
            val distancesM = measurements.map { it.distanceMm / 1000.0 }
            val meanDistM = distancesM.average()
            val variance = distancesM.map { (it - meanDistM) * (it - meanDistM) }.average()
            val stdDevM = sqrt(variance)

            // rssi_ref: average RSSI from measurements where corrected dist is in [minDistM, maxDistM]
            val inRange = measurements.filter { m ->
                val d = m.distanceMm / 1000.0
                d in minDistM..maxDistM
            }
            val rssiRef = if (inRange.isNotEmpty()) {
                inRange.map { it.rssi }.average()
            } else {
                measurements.map { it.rssi }.average()
            }

            return Triple(meanDistM, stdDevM, rssiRef)
        }
    }
}
