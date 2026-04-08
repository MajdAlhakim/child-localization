package qa.qu.trakn.aptool

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import coil.Coil
import coil.ImageLoader
import okhttp3.OkHttpClient
import qa.qu.trakn.aptool.data.SettingsRepository
import qa.qu.trakn.aptool.ui.MainScreen
import qa.qu.trakn.aptool.ui.map.MapViewModel
import qa.qu.trakn.aptool.ui.scan.ScanViewModel
import qa.qu.trakn.aptool.ui.settings.SettingsViewModel
import qa.qu.trakn.aptool.ui.status.StatusViewModel
import qa.qu.trakn.aptool.ui.theme.TRAKNTheme
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

class MainActivity : ComponentActivity() {

    private val requiredPermissions = arrayOf(
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION,
        Manifest.permission.ACCESS_WIFI_STATE,
        Manifest.permission.CHANGE_WIFI_STATE,
    )

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        setupCompose()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Configure Coil's global ImageLoader to trust the server's self-signed certificate.
        // Without this, every AsyncImage targeting https://35.238.189.188 fails with SSL errors.
        val trustAll = arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        })
        val sslCtx = SSLContext.getInstance("TLS").apply { init(null, trustAll, SecureRandom()) }
        val sslOkHttp = OkHttpClient.Builder()
            .sslSocketFactory(sslCtx.socketFactory, trustAll[0] as X509TrustManager)
            .hostnameVerifier { _, _ -> true }
            .build()
        Coil.setImageLoader(
            ImageLoader.Builder(applicationContext)
                .okHttpClient { sslOkHttp }
                .build()
        )

        val allGranted = requiredPermissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
        if (allGranted) setupCompose() else permissionLauncher.launch(requiredPermissions)
    }

    private fun setupCompose() {
        val settingsRepo = SettingsRepository(applicationContext)
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = when {
                modelClass.isAssignableFrom(ScanViewModel::class.java)   -> ScanViewModel(applicationContext, settingsRepo) as T
                modelClass.isAssignableFrom(MapViewModel::class.java)    -> MapViewModel(applicationContext, settingsRepo) as T
                modelClass.isAssignableFrom(StatusViewModel::class.java) -> StatusViewModel(applicationContext, settingsRepo) as T
                modelClass.isAssignableFrom(SettingsViewModel::class.java) -> SettingsViewModel(applicationContext, settingsRepo) as T
                else -> throw IllegalArgumentException("Unknown ViewModel: $modelClass")
            }
        }

        val scanVM     = ViewModelProvider(this, factory)[ScanViewModel::class.java]
        val mapVM      = ViewModelProvider(this, factory)[MapViewModel::class.java]
        val statusVM   = ViewModelProvider(this, factory)[StatusViewModel::class.java]
        val settingsVM = ViewModelProvider(this, factory)[SettingsViewModel::class.java]

        setContent {
            TRAKNTheme {
                MainScreen(
                    scanViewModel = scanVM,
                    mapViewModel = mapVM,
                    statusViewModel = statusVM,
                    settingsViewModel = settingsVM,
                )
            }
        }
    }
}
