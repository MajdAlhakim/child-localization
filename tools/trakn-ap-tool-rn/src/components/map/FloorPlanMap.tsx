import React, { useState, useCallback } from 'react';
import { View, Image, StyleSheet, ActivityIndicator, Text } from 'react-native';
import { GestureDetector, Gesture } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue, useAnimatedStyle,
  withSpring, runOnJS,
} from 'react-native-reanimated';
import Svg, {
  Circle, G, Text as SvgText, Line, Rect,
} from 'react-native-svg';
import { C } from '../../theme';
import type { ApEntry, GridResponse } from '../../api/client';

interface Props {
  floorPlanUrl: string | null;
  aps:          ApEntry[];
  grid?:        GridResponse | null;
  scalePxPerM?: number;
  onTap?:       (xMeters: number, yMeters: number) => void;
  // For parent app: position marker
  position?:    { x: number; y: number; error?: number } | null;
}

export default function FloorPlanMap({ floorPlanUrl, aps, grid, scalePxPerM = 10, onTap, position }: Props) {
  const [containerW, setContainerW]     = useState(0);
  const [containerH, setContainerH]     = useState(0);
  const [naturalW, setNaturalW]         = useState(1);
  const [naturalH, setNaturalH]         = useState(1);
  const [imageLoaded, setImageLoaded]   = useState(false);

  // Gesture state
  const zoom       = useSharedValue(1);
  const savedZoom  = useSharedValue(1);
  const panX       = useSharedValue(0);
  const panY       = useSharedValue(0);
  const savedPanX  = useSharedValue(0);
  const savedPanY  = useSharedValue(0);

  // Display scale = fit image to container width
  const displayScale = containerW > 0 && naturalW > 0 ? containerW / naturalW : 1;
  const displayW = naturalW * displayScale;
  const displayH = naturalH * displayScale;

  // Pan gesture
  const panGesture = Gesture.Pan()
    .minDistance(5)
    .onUpdate(e => {
      panX.value = savedPanX.value + e.translationX;
      panY.value = savedPanY.value + e.translationY;
    })
    .onEnd(() => {
      savedPanX.value = panX.value;
      savedPanY.value = panY.value;
    });

  // Pinch gesture
  const pinchGesture = Gesture.Pinch()
    .onUpdate(e => { zoom.value = Math.max(0.5, Math.min(8, savedZoom.value * e.scale)); })
    .onEnd(() => { savedZoom.value = zoom.value; });

  // Tap gesture (for AP placement)
  const handleTapImpl = useCallback((lx: number, ly: number) => {
    if (!onTap) return;
    // lx, ly are relative to the Animated.View (displayed image space)
    const naturalX = lx / displayScale;
    const naturalY = ly / displayScale;
    const xM = naturalX / scalePxPerM;
    const yM = naturalY / scalePxPerM;
    onTap(xM, yM);
  }, [onTap, displayScale, scalePxPerM]);

  const tapGesture = Gesture.Tap()
    .maxDuration(200)
    .onEnd(e => { runOnJS(handleTapImpl)(e.x, e.y); });

  const composed = Gesture.Simultaneous(
    Gesture.Simultaneous(pinchGesture, panGesture),
    tapGesture,
  );

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: panX.value },
      { translateY: panY.value },
      { scale: zoom.value },
    ],
  }));

  // Error ring color for parent app position marker
  function positionColor(error?: number) {
    if (!error) return C.primary;
    if (error < 5)  return C.green;
    if (error < 10) return C.yellow;
    return C.red;
  }

  if (!floorPlanUrl) {
    return (
      <View style={styles.placeholder}>
        <Text style={styles.placeholderText}>No floor plan loaded</Text>
        <Text style={{ color: C.textDim, fontSize: 12, marginTop: 4 }}>Upload a floor plan via the Web Mapping Tool</Text>
      </View>
    );
  }

  return (
    <View
      style={styles.container}
      onLayout={e => {
        setContainerW(e.nativeEvent.layout.width);
        setContainerH(e.nativeEvent.layout.height);
      }}
    >
      <GestureDetector gesture={composed}>
        <Animated.View style={[{ width: displayW, height: displayH }, animStyle]}>
          <Image
            source={{ uri: floorPlanUrl }}
            style={{ width: displayW, height: displayH }}
            resizeMode="contain"
            onLoad={e => {
              setNaturalW(e.nativeEvent.source.width);
              setNaturalH(e.nativeEvent.source.height);
              setImageLoaded(true);
            }}
          />

          {imageLoaded && (
            <Svg style={StyleSheet.absoluteFill} width={displayW} height={displayH}>
              {/* Grid overlay */}
              {grid?.points.map((pt, i) => (
                <Circle
                  key={i}
                  cx={pt.x * scalePxPerM * displayScale}
                  cy={pt.y * scalePxPerM * displayScale}
                  r={2}
                  fill="rgba(124,58,237,0.6)"
                />
              ))}

              {/* AP markers */}
              {aps.map(ap => {
                const cx = ap.x * scalePxPerM * displayScale;
                const cy = ap.y * scalePxPerM * displayScale;
                return (
                  <G key={ap.bssid} x={cx} y={cy}>
                    {/* Signal rings */}
                    {[28, 20, 13].map((r, i) => (
                      <Circle key={i} r={r} fill="transparent" stroke={`rgba(249,115,22,${0.12 - i * 0.03})`} strokeWidth={1} />
                    ))}
                    <Circle r={13} fill="transparent" stroke="rgba(249,115,22,0.4)" strokeWidth={1.5} />
                    <Circle r={7} fill={C.primary} stroke="white" strokeWidth={1} />
                    <SvgText
                      fontSize={8} fill={C.primary} textAnchor="middle" y={20}
                      fontFamily="monospace"
                    >
                      {ap.bssid.slice(-8)}
                    </SvgText>
                  </G>
                );
              })}

              {/* Position marker (parent app) */}
              {position && (() => {
                const cx = position.x * scalePxPerM * displayScale;
                const cy = position.y * scalePxPerM * displayScale;
                const col = positionColor(position.error);
                return (
                  <G key="pos" x={cx} y={cy}>
                    {/* Outer pulse ring */}
                    <Circle r={22} fill="transparent" stroke={col} strokeWidth={1} opacity={0.4} />
                    <Circle r={15} fill={`${col}30`} stroke={col} strokeWidth={1.5} opacity={0.7} />
                    {/* Crosshair lines */}
                    <Line x1={-18} y1={0} x2={-10} y2={0} stroke={col} strokeWidth={1.5} />
                    <Line x1={10}  y1={0} x2={18}  y2={0} stroke={col} strokeWidth={1.5} />
                    <Line x1={0} y1={-18} x2={0} y2={-10} stroke={col} strokeWidth={1.5} />
                    <Line x1={0} y1={10}  x2={0} y2={18}  stroke={col} strokeWidth={1.5} />
                    {/* Center dot */}
                    <Circle r={6} fill={col} />
                    <Circle r={3} fill="white" />
                  </G>
                );
              })()}
            </Svg>
          )}

          {!imageLoaded && (
            <View style={[StyleSheet.absoluteFill, styles.loading]}>
              <ActivityIndicator color={C.primary} size="large" />
            </View>
          )}
        </Animated.View>
      </GestureDetector>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#050810',
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#050810',
  },
  placeholderText: {
    color: '#526a85',
    fontSize: 14,
    fontWeight: '500',
  },
  loading: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(6,10,16,0.8)',
  },
});
