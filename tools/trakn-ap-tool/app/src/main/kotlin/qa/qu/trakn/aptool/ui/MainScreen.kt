package qa.qu.trakn.aptool.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.Wifi
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import qa.qu.trakn.aptool.ui.map.MapScreen
import qa.qu.trakn.aptool.ui.map.MapViewModel
import qa.qu.trakn.aptool.ui.scan.ScanScreen
import qa.qu.trakn.aptool.ui.scan.ScanViewModel
import qa.qu.trakn.aptool.ui.settings.SettingsScreen
import qa.qu.trakn.aptool.ui.settings.SettingsViewModel
import qa.qu.trakn.aptool.ui.status.StatusScreen
import qa.qu.trakn.aptool.ui.status.StatusViewModel
import qa.qu.trakn.aptool.ui.theme.Orange

sealed class Screen(val route: String, val label: String) {
    object Scan   : Screen("scan", "Scan")
    object Map    : Screen("map", "Map")
    object Status : Screen("status", "Status")
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    scanViewModel: ScanViewModel,
    mapViewModel: MapViewModel,
    statusViewModel: StatusViewModel,
    settingsViewModel: SettingsViewModel,
) {
    val navController = rememberNavController()
    var showSettings by remember { mutableStateOf(false) }

    if (showSettings) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Settings", fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold) },
                    navigationIcon = {
                        IconButton(onClick = { showSettings = false }) {
                            Icon(Icons.Default.Settings, contentDescription = null, tint = Orange)
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
                )
            }
        ) { padding ->
            androidx.compose.foundation.layout.Box(Modifier.padding(padding)) {
                SettingsScreen(settingsViewModel)
            }
        }
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        "TRAKN AP Tool",
                        fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.Bold,
                        color = Orange,
                    )
                },
                actions = {
                    IconButton(onClick = { showSettings = true }) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings", tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f))
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                val navBackStackEntry by navController.currentBackStackEntryAsState()
                val currentDest = navBackStackEntry?.destination

                NavigationBarItem(
                    selected = currentDest?.hierarchy?.any { it.route == Screen.Scan.route } == true,
                    onClick = { navController.navigate(Screen.Scan.route) { launchSingleTop = true } },
                    icon = {
                        Icon(
                            if (currentDest?.route == Screen.Scan.route) Icons.Filled.Wifi else Icons.Outlined.Wifi,
                            contentDescription = null,
                        )
                    },
                    label = { Text(Screen.Scan.label) },
                    colors = NavigationBarItemDefaults.colors(indicatorColor = Orange.copy(alpha = 0.15f), selectedIconColor = Orange, selectedTextColor = Orange),
                )
                NavigationBarItem(
                    selected = currentDest?.hierarchy?.any { it.route == Screen.Map.route } == true,
                    onClick = { navController.navigate(Screen.Map.route) { launchSingleTop = true } },
                    icon = {
                        Icon(
                            if (currentDest?.route == Screen.Map.route) Icons.Filled.Map else Icons.Outlined.Map,
                            contentDescription = null,
                        )
                    },
                    label = { Text(Screen.Map.label) },
                    colors = NavigationBarItemDefaults.colors(indicatorColor = Orange.copy(alpha = 0.15f), selectedIconColor = Orange, selectedTextColor = Orange),
                )
                NavigationBarItem(
                    selected = currentDest?.hierarchy?.any { it.route == Screen.Status.route } == true,
                    onClick = { navController.navigate(Screen.Status.route) { launchSingleTop = true } },
                    icon = {
                        Icon(
                            if (currentDest?.route == Screen.Status.route) Icons.Filled.Info else Icons.Outlined.Info,
                            contentDescription = null,
                        )
                    },
                    label = { Text(Screen.Status.label) },
                    colors = NavigationBarItemDefaults.colors(indicatorColor = Orange.copy(alpha = 0.15f), selectedIconColor = Orange, selectedTextColor = Orange),
                )
            }
        }
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Screen.Scan.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(Screen.Scan.route) {
                ScanScreen(viewModel = scanViewModel)
            }
            composable(Screen.Map.route) {
                MapScreen(
                    viewModel = mapViewModel,
                    scanViewModel = scanViewModel,
                )
            }
            composable(Screen.Status.route) {
                StatusScreen(statusViewModel)
            }
        }
    }
}
