package qa.qu.trakn.aptool.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import qa.qu.trakn.aptool.ui.theme.Blue
import qa.qu.trakn.aptool.ui.theme.Green
import qa.qu.trakn.aptool.ui.theme.Orange
import qa.qu.trakn.aptool.ui.theme.Red

@Composable
fun SettingsScreen(viewModel: SettingsViewModel) {
    val state by viewModel.state.collectAsState()
    val s = state.settings
    var showApiKey by remember { mutableStateOf(false) }

    // Floor plan picker dialog
    if (state.showFloorPlanPicker) {
        AlertDialog(
            onDismissRequest = { viewModel.dismissFloorPlanPicker() },
            title = { Text("Select Floor Plan", fontWeight = FontWeight.Bold) },
            text = {
                Box(modifier = Modifier.height(360.dp)) {
                    when {
                        state.isLoadingVenues -> {
                            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                CircularProgressIndicator(color = Orange)
                            }
                        }
                        state.venueLoadError != null -> {
                            Text(
                                "Failed to load: ${state.venueLoadError}",
                                color = Red, fontSize = 12.sp, fontFamily = FontFamily.Monospace,
                            )
                        }
                        state.venues.isEmpty() -> {
                            Text(
                                "No venues found. Create a venue and upload a floor plan in the Web Mapping Tool first.",
                                fontSize = 12.sp,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                            )
                        }
                        else -> {
                            LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                state.venues.forEach { venue ->
                                    item {
                                        Text(
                                            venue.name,
                                            fontWeight = FontWeight.SemiBold,
                                            fontSize = 13.sp,
                                            color = Orange,
                                            modifier = Modifier.padding(vertical = 4.dp),
                                        )
                                    }
                                    if (venue.floorPlans.isEmpty()) {
                                        item {
                                            Text(
                                                "  No floor plans",
                                                fontSize = 11.sp,
                                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f),
                                            )
                                        }
                                    }
                                    items(venue.floorPlans) { fp ->
                                        val isSelected = fp.id == s.selectedFloorPlanId
                                        Card(
                                            colors = CardDefaults.cardColors(
                                                containerColor = if (isSelected)
                                                    Orange.copy(alpha = 0.15f)
                                                else
                                                    MaterialTheme.colorScheme.surfaceVariant,
                                            ),
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable { viewModel.selectFloorPlan(fp, venue.name) },
                                        ) {
                                            Column(Modifier.padding(10.dp)) {
                                                Text(
                                                    "Floor ${fp.floorNumber}  —  ${fp.name}",
                                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                                    fontSize = 13.sp,
                                                )
                                                Text(
                                                    "${fp.apCount} APs · ${if (fp.hasImage) "has image" else "no image"}",
                                                    fontSize = 11.sp,
                                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = {},
            dismissButton = {
                TextButton(onClick = { viewModel.dismissFloorPlanPicker() }) { Text("Cancel") }
            },
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Settings", fontWeight = FontWeight.Bold, fontSize = 18.sp)

        SectionCard("Backend") {
            OutlinedTextField(
                value = s.apiBaseUrl,
                onValueChange = { viewModel.updateBaseUrl(it); viewModel.save() },
                label = { Text("API Base URL") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = s.apiKey,
                onValueChange = { viewModel.updateApiKey(it); viewModel.save() },
                label = { Text("API Key") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                visualTransformation = if (showApiKey) VisualTransformation.None else PasswordVisualTransformation(),
                trailingIcon = {
                    androidx.compose.material3.TextButton(onClick = { showApiKey = !showApiKey }) {
                        Text(if (showApiKey) "Hide" else "Show", fontSize = 11.sp)
                    }
                },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            )
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { viewModel.testConnection() },
                    enabled = !state.isTesting,
                    colors = ButtonDefaults.buttonColors(containerColor = Blue),
                    modifier = Modifier.weight(1f),
                ) {
                    if (state.isTesting) {
                        CircularProgressIndicator(modifier = androidx.compose.ui.Modifier.height(16.dp).padding(end = 4.dp), strokeWidth = 2.dp, color = androidx.compose.ui.graphics.Color.White)
                    }
                    Text("Test Connection")
                }
            }
            if (state.testResult != null) {
                val color = if (state.testResult!!.startsWith("✓")) Green else Red
                Text(
                    state.testResult!!,
                    color = color, fontFamily = FontFamily.Monospace, fontSize = 12.sp,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }

        SectionCard("Floor Plan") {
            if (s.selectedFloorPlanId.isNotEmpty()) {
                Text(
                    s.selectedFloorPlanDisplay,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    "ID: ${s.selectedFloorPlanId}",
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f),
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            } else {
                Text(
                    "No floor plan selected. Tap below to choose which floor you are mapping.",
                    fontSize = 12.sp,
                    color = Red,
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            }
            OutlinedButton(
                onClick = { viewModel.openFloorPlanPicker() },
                modifier = Modifier.fillMaxWidth(),
                border = androidx.compose.foundation.BorderStroke(1.dp, Orange),
            ) {
                Text(
                    if (s.selectedFloorPlanId.isEmpty()) "Select Floor Plan" else "Change Floor Plan",
                    color = Orange,
                )
            }
        }

        SectionCard("One-Sided RTT Offset Calibration") {
            Text(
                "One-sided RTT works with all APs. The raw reading includes the AP's turn-around " +
                "time (SIFS ≈ 16 µs → ~2400–2700 m). Set this offset to match your AP model " +
                "by measuring at a known distance and adjusting until the reading is correct.",
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                modifier = Modifier.padding(bottom = 6.dp),
            )
            LabelRow("One-sided RTT offset", "${"%.0f".format(s.oneSidedRttOffsetM)} m")
            Slider(
                value = s.oneSidedRttOffsetM.toFloat(),
                onValueChange = { viewModel.updateOneSidedOffset(it.toDouble()); viewModel.save() },
                valueRange = 2000f..3000f,
                colors = SliderDefaults.colors(thumbColor = Orange, activeTrackColor = Orange),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("2000 m", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                Text("Default: 2500 m", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
                Text("3000 m", fontSize = 10.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f))
            }
        }

        SectionCard("RTT Measurements") {
            LabelRow("Measurements per session", "${s.rttMeasurementsPerSession}")
            Slider(
                value = s.rttMeasurementsPerSession.toFloat(),
                onValueChange = { viewModel.updateRttCount(it.toInt()); viewModel.save() },
                valueRange = 10f..50f,
                steps = 7,
                colors = SliderDefaults.colors(thumbColor = Orange, activeTrackColor = Orange),
            )

            HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f), modifier = Modifier.padding(vertical = 4.dp))

            LabelRow("Min RTT dist for RSSI ref", "${"%.1f".format(s.rttMinDistM)} m")
            Slider(
                value = s.rttMinDistM.toFloat(),
                onValueChange = { viewModel.updateRttMin(it.toDouble()); viewModel.save() },
                valueRange = 0.2f..2f,
                colors = SliderDefaults.colors(thumbColor = Blue, activeTrackColor = Blue),
            )

            LabelRow("Max RTT dist for RSSI ref", "${"%.1f".format(s.rttMaxDistM)} m")
            Slider(
                value = s.rttMaxDistM.toFloat(),
                onValueChange = { viewModel.updateRttMax(it.toDouble()); viewModel.save() },
                valueRange = 0.5f..3f,
                colors = SliderDefaults.colors(thumbColor = Blue, activeTrackColor = Blue),
            )
        }

        SectionCard("About") {
            Text("TRAKN AP Localization Tool", fontWeight = FontWeight.SemiBold)
            Text("Version 1.0 — Qatar University Senior Design", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f))
            Text("Min SDK: API 31 (Android 12)", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.4f), fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, color = Orange, modifier = Modifier.padding(bottom = 8.dp))
            content()
        }
    }
}

@Composable
fun LabelRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
        Text(value, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
    }
}
