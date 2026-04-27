package qa.qu.trakn.parentapp.ui.locate

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import qa.qu.trakn.parentapp.data.models.FloorPlanInfo
import qa.qu.trakn.parentapp.ui.theme.Blue
import qa.qu.trakn.parentapp.ui.theme.Green
import qa.qu.trakn.parentapp.ui.theme.Orange
import qa.qu.trakn.parentapp.ui.theme.Red
import qa.qu.trakn.parentapp.ui.theme.Yellow

private fun floorLabel(n: Int): String = when (n) {
    -1   -> "Basement"
    0    -> "Ground"
    1    -> "Floor 1"
    else -> "Floor $n"
}

@Composable
fun LocateScreen(viewModel: LocateViewModel) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current

    LaunchedEffect(Unit) { viewModel.startTracking() }

    var imgNaturalW by remember { mutableFloatStateOf(595f) }
    var imgNaturalH by remember { mutableFloatStateOf(842f) }
    var panelExpanded by remember { mutableStateOf(true) }

    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val pulseScale by infiniteTransition.animateFloat(
        initialValue  = 1f,
        targetValue   = 1.6f,
        animationSpec = infiniteRepeatable(
            animation  = tween(1000, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulseScale",
    )

    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {

        // ── Floor plan + canvas ──────────────────────────────────────────────
        Box(
            modifier = Modifier
                .fillMaxSize()
                .clickable(enabled = state.floorMenuOpen) { viewModel.dismissFloorMenu() },
        ) {
            if (state.floorPlanUrl != null) {
                AsyncImage(
                    model = ImageRequest.Builder(context)
                        .data(state.floorPlanUrl)
                        .crossfade(true)
                        .build(),
                    contentDescription = "Floor plan",
                    contentScale = ContentScale.Fit,
                    onSuccess = { result ->
                        imgNaturalW = result.painter.intrinsicSize.width.takeIf  { it > 0 } ?: 595f
                        imgNaturalH = result.painter.intrinsicSize.height.takeIf { it > 0 } ?: 842f
                    },
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("No floor plan uploaded", color = Yellow,
                            fontSize = 15.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            state.floorPlanError ?: "Upload via Web Mapping Tool.",
                            color    = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.5f),
                            fontSize = 12.sp,
                        )
                    }
                }
            }

            Canvas(modifier = Modifier.fillMaxSize()) {
                val canvasW  = size.width
                val canvasH  = size.height
                val fitScale = minOf(canvasW / imgNaturalW, canvasH / imgNaturalH)
                val startX   = (canvasW - imgNaturalW * fitScale) / 2
                val startY   = (canvasH - imgNaturalH * fitScale) / 2

                fun toCanvas(x: Double, y: Double) = Offset(
                    x = startX + x.toFloat() * SCALE_PX_PER_M * fitScale,
                    y = startY + y.toFloat() * SCALE_PX_PER_M * fitScale,
                )

                // AP dots (faint orange)
                state.knownAps.forEach { ap ->
                    val center = toCanvas(ap.x, ap.y)
                    drawCircle(Orange.copy(alpha = 0.12f), radius = 18f, center = center)
                    drawCircle(Orange.copy(alpha = 0.5f),  radius = 4f,  center = center)
                }

                val childCenter  = state.childEstimate?.let  { toCanvas(it.xM, it.yM) }
                val parentCenter = state.parentEstimate?.let { toCanvas(it.xM, it.yM) }

                // Dashed line connecting parent to child
                if (childCenter != null && parentCenter != null) {
                    val lineColor = if (state.alertActive) Red.copy(alpha = 0.6f)
                                    else Color.Gray.copy(alpha = 0.45f)
                    drawLine(
                        color       = lineColor,
                        start       = parentCenter,
                        end         = childCenter,
                        strokeWidth = 2.5f,
                        pathEffect  = PathEffect.dashPathEffect(floatArrayOf(12f, 8f)),
                    )
                }

                // Parent dot — green filled circle
                if (parentCenter != null) {
                    drawCircle(Green.copy(alpha = 0.20f), radius = 22f, center = parentCenter)
                    drawCircle(Green.copy(alpha = 0.85f), radius = 10f, center = parentCenter)
                    drawCircle(Color.White.copy(alpha = 0.6f), radius = 4f, center = parentCenter)
                }

                // Child dot — blue with pulsing ring
                if (childCenter != null) {
                    val inBounds = childCenter.x in -40f..(canvasW + 40f) &&
                                   childCenter.y in -40f..(canvasH + 40f)
                    if (inBounds) {
                        val ringColor = if (state.alertActive) Red else Blue
                        drawCircle(ringColor.copy(alpha = 0.10f),
                            radius = 36f * pulseScale, center = childCenter)
                        drawCircle(ringColor.copy(alpha = 0.20f), radius = 30f, center = childCenter)
                        drawCircle(ringColor, radius = 30f, center = childCenter, style = Stroke(1.5f))
                        drawCircle(Color.Black.copy(alpha = 0.20f), radius = 13f,
                            center = childCenter.copy(y = childCenter.y + 2f))
                        drawCircle(Color.White, radius = 12f, center = childCenter)
                        drawCircle(Blue,        radius = 9f,  center = childCenter)
                    }
                }
            }
        }

        // ── Floor picker — top-right ─────────────────────────────────────────
        if (state.availableFloors.isNotEmpty()) {
            Box(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(top = 12.dp, end = 12.dp),
            ) {
                Column(horizontalAlignment = Alignment.End) {
                    // Trigger pill
                    val selLabel = state.selectedFloorNumber?.let { floorLabel(it) } ?: "Floor"
                    Row(
                        modifier = Modifier
                            .clip(RoundedCornerShape(50))
                            .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.95f))
                            .clickable { viewModel.toggleFloorMenu() }
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(
                            text       = selLabel,
                            fontSize   = 12.sp,
                            fontWeight = FontWeight.SemiBold,
                            fontFamily = FontFamily.Monospace,
                            color      = MaterialTheme.colorScheme.onSurface,
                        )
                        Text(
                            text     = if (state.floorMenuOpen) "▲" else "▾",
                            fontSize = 10.sp,
                            color    = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                        )
                    }

                    // Dropdown menu
                    AnimatedVisibility(visible = state.floorMenuOpen) {
                        Column(
                            modifier = Modifier
                                .padding(top = 4.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.97f))
                                .padding(vertical = 6.dp),
                        ) {
                            state.availableFloors.forEach { fp ->
                                FloorMenuItem(
                                    fp             = fp,
                                    isSelected     = fp.id == state.selectedFloorPlanId,
                                    isTagHere      = fp.floorNumber == state.tagFloorNumber,
                                    onClick        = { viewModel.selectFloor(fp) },
                                )
                            }
                        }
                    }
                }
            }
        }

        // ── Collapsed pill ───────────────────────────────────────────────────
        AnimatedVisibility(
            visible  = !panelExpanded,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 12.dp),
            enter    = slideInVertically { it },
            exit     = slideOutVertically { it },
        ) {
            val dist     = state.distanceM
            val dotColor = when {
                state.alertActive    -> Red
                dist != null         -> Green
                state.wsConnected    -> Yellow
                else                 -> Red
            }
            Row(
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.95f))
                    .clickable { panelExpanded = true }
                    .padding(horizontal = 18.dp, vertical = 10.dp),
                verticalAlignment     = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(dotColor))
                Text(
                    text = when {
                        dist != null -> "${"%.1f".format(dist)} m away"
                        else         -> state.statusMsg
                    },
                    fontSize   = 12.sp,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.SemiBold,
                    color      = if (state.alertActive) Red
                                 else MaterialTheme.colorScheme.onSurface,
                )
                if (!state.wsConnected) {
                    CircularProgressIndicator(
                        modifier    = Modifier.size(12.dp),
                        strokeWidth = 1.5.dp,
                        color       = Orange,
                    )
                }
            }
        }

        // ── Status panel ─────────────────────────────────────────────────────
        AnimatedVisibility(
            visible  = panelExpanded,
            modifier = Modifier.align(Alignment.BottomCenter),
            enter    = slideInVertically { it },
            exit     = slideOutVertically { it },
        ) {
            StatusPanel(
                state      = state,
                onCollapse = { panelExpanded = false },
                onRefresh  = { viewModel.refresh() },
            )
        }
    }
}

// ── Floor menu item ───────────────────────────────────────────────────────────

@Composable
private fun FloorMenuItem(
    fp: FloorPlanInfo,
    isSelected: Boolean,
    isTagHere: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .background(
                if (isSelected) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)
                else Color.Transparent
            )
            .padding(horizontal = 16.dp, vertical = 9.dp),
        verticalAlignment     = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(
            verticalAlignment     = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // Selection indicator
            Box(
                modifier = Modifier
                    .size(6.dp)
                    .clip(CircleShape)
                    .background(
                        if (isSelected) MaterialTheme.colorScheme.primary
                        else Color.Transparent
                    ),
            )
            Text(
                text       = floorLabel(fp.floorNumber),
                fontSize   = 13.sp,
                fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
                fontFamily = FontFamily.Monospace,
                color      = if (isSelected) MaterialTheme.colorScheme.primary
                             else MaterialTheme.colorScheme.onSurface,
            )
        }

        // Tag location dot — shown when tag is on this floor
        if (isTagHere) {
            Row(
                verticalAlignment     = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(7.dp)
                        .clip(CircleShape)
                        .background(Blue),
                )
                Text(
                    text     = "tag",
                    fontSize = 9.sp,
                    color    = Blue,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }
    }
}

// ── Status panel ─────────────────────────────────────────────────────────────

@Composable
private fun StatusPanel(
    state:      LocateUiState,
    onCollapse: () -> Unit,
    onRefresh:  () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp))
            .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.97f))
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        // ── Header ────────────────────────────────────────────────────────────
        Row(
            modifier              = Modifier.fillMaxWidth(),
            verticalAlignment     = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val dotColor = if (state.wsConnected) Green else Red
                Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(dotColor))
                Spacer(Modifier.width(8.dp))
                Text(
                    text = if (state.wsConnected) "Tracking ${state.tagId}"
                           else state.statusMsg,
                    fontWeight = FontWeight.SemiBold,
                    fontSize   = 13.sp,
                )
            }
            Row(
                verticalAlignment     = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (!state.wsConnected) {
                    CircularProgressIndicator(
                        modifier    = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color       = Orange,
                    )
                }
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .clickable { onRefresh() }
                        .padding(horizontal = 10.dp, vertical = 4.dp),
                ) {
                    Text("↺ Retry", fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .clickable { onCollapse() }
                        .padding(horizontal = 10.dp, vertical = 4.dp),
                ) {
                    Text("▼ Hide", fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
            }
        }

        // ── Floor info row ────────────────────────────────────────────────────
        val tagFloor = state.tagFloorNumber
        val selFloor = state.selectedFloorNumber
        if (tagFloor != null || selFloor != null) {
            Row(
                modifier              = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (selFloor != null) {
                    InfoChip(
                        label    = "VIEWING",
                        value    = floorLabel(selFloor),
                        color    = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.weight(1f),
                    )
                }
                if (tagFloor != null) {
                    InfoChip(
                        label    = "TAG ON",
                        value    = floorLabel(tagFloor),
                        color    = Blue,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }

        // ── Distance card ─────────────────────────────────────────────────────
        val dist = state.distanceM
        if (dist != null) {
            val (distColor, distLabel) = when {
                dist < 10.0 -> Green  to "Nearby"
                dist < 20.0 -> Yellow to "Getting further"
                else        -> Red    to "Too far away!"
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(
                        if (state.alertActive) Red.copy(alpha = 0.10f)
                        else MaterialTheme.colorScheme.surfaceVariant
                    )
                    .padding(horizontal = 14.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment     = Alignment.CenterVertically,
            ) {
                Column {
                    Text("DISTANCE", fontSize = 9.sp, letterSpacing = 1.sp,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f))
                    Text(
                        "${"%.1f".format(dist)} m",
                        fontSize   = 22.sp,
                        fontWeight = FontWeight.Bold,
                        color      = distColor,
                        fontFamily = FontFamily.Monospace,
                    )
                }
                Text(
                    distLabel,
                    fontSize   = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    color      = distColor,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }

        // ── Child + parent position row ───────────────────────────────────────
        if (state.childEstimate != null || state.parentEstimate != null) {
            Row(
                modifier              = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                state.childEstimate?.let { c ->
                    PositionChip(
                        label = "CHILD",
                        x     = c.xM,
                        y     = c.yM,
                        color = Blue,
                        modifier = Modifier.weight(1f),
                    )
                }
                state.parentEstimate?.let { p ->
                    PositionChip(
                        label = "YOU",
                        x     = p.xM,
                        y     = p.yM,
                        color = Green,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoChip(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 10.dp, vertical = 8.dp),
    ) {
        Text(label, fontSize = 9.sp, letterSpacing = 1.sp,
            fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f))
        Text(
            value,
            fontSize   = 12.sp,
            fontWeight = FontWeight.SemiBold,
            color      = color,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun PositionChip(
    label: String,
    x: Double,
    y: Double,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 10.dp, vertical = 8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(6.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(5.dp))
            Text(label, fontSize = 9.sp, letterSpacing = 1.sp,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f))
        }
        Text(
            "${"%.1f".format(x)}, ${"%.1f".format(y)} m",
            fontSize   = 11.sp,
            fontWeight = FontWeight.SemiBold,
            color      = color,
            fontFamily = FontFamily.Monospace,
        )
    }
}
