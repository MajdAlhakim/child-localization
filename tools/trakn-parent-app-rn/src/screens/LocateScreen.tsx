import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  Animated as RNAnimated, Dimensions,
} from 'react-native';
import { useStore } from '../store';
import { apApi, gridApi, getFloorPlanUrl } from '../api/client';
import { useWifiScan } from '../hooks/useWifiScan';
import { useLocalization } from '../hooks/useLocalization';
import FloorPlanMap from '../components/map/FloorPlanMap';
import { C, S, F } from '../theme';

const { width: SW } = Dimensions.get('window');

function AccuracyBadge({ error }: { error: number }) {
  if (error < 3)  return <View style={[badge.wrap, { backgroundColor: C.green  + '20', borderColor: C.green  + '60' }]}><Text style={[badge.text, { color: C.green  }]}>High accuracy  &lt;3m</Text></View>;
  if (error < 6)  return <View style={[badge.wrap, { backgroundColor: C.yellow + '20', borderColor: C.yellow + '60' }]}><Text style={[badge.text, { color: C.yellow }]}>Medium  ~{error.toFixed(1)}m</Text></View>;
  return              <View style={[badge.wrap, { backgroundColor: C.red    + '20', borderColor: C.red    + '60' }]}><Text style={[badge.text, { color: C.red    }]}>Low accuracy  ~{error.toFixed(1)}m</Text></View>;
}

const badge = StyleSheet.create({
  wrap: { borderRadius: 8, borderWidth: 1, paddingHorizontal: 10, paddingVertical: 4 },
  text: { fontSize: 11, fontFamily: F.mono, fontWeight: '600' },
});

function PulseRing({ active }: { active: boolean }) {
  const anim = useRef(new RNAnimated.Value(0)).current;
  useEffect(() => {
    if (!active) { anim.setValue(0); return; }
    const loop = RNAnimated.loop(
      RNAnimated.sequence([
        RNAnimated.timing(anim, { toValue: 1, duration: 1200, useNativeDriver: true }),
        RNAnimated.timing(anim, { toValue: 0, duration: 0,    useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [active]);

  const scale   = anim.interpolate({ inputRange: [0, 1], outputRange: [1, 1.5] });
  const opacity = anim.interpolate({ inputRange: [0, 0.7, 1], outputRange: [0.6, 0.2, 0] });

  return (
    <RNAnimated.View
      style={{
        position: 'absolute', width: 16, height: 16, borderRadius: 8,
        borderWidth: 2, borderColor: C.primary,
        transform: [{ scale }], opacity,
      }}
    />
  );
}

export default function LocateScreen() {
  const position       = useStore(s => s.position);
  const isLocating     = useStore(s => s.isLocating);
  const locateError    = useStore(s => s.locateError);
  const trackingActive = useStore(s => s.trackingActive);
  const setTracking    = useStore(s => s.setTracking);
  const setServerAps   = useStore(s => s.setServerAps);
  const setGrid        = useStore(s => s.setGrid);
  const setOnline      = useStore(s => s.setOnline);
  const networks       = useStore(s => s.networks);
  const serverAps      = useStore(s => s.serverAps);
  const grid           = useStore(s => s.grid);
  const scalePxPerM    = useStore(s => s.scalePxPerM);
  const isScanning     = useStore(s => s.isScanning);

  const [floorPlanUrl, setFloorPlanUrl] = useState<string | null>(null);
  const [panelExpanded, setPanelExpanded] = useState(false);

  const { rescan } = useWifiScan(10_000);
  useLocalization(trackingActive);

  useEffect(() => {
    const boot = async () => {
      const { checkHealth } = await import('../api/client');
      const online = await checkHealth();
      setOnline(online);
      const [url, apsRes, gridRes] = await Promise.all([
        getFloorPlanUrl(),
        apApi.list().catch(() => null),
        gridApi.get().catch(() => null),
      ]);
      setFloorPlanUrl(url);
      if (apsRes) setServerAps(apsRes.access_points);
      if (gridRes) setGrid(gridRes);
    };
    boot();
  }, []);

  return (
    <View style={styles.root}>
      {/* Map fills screen */}
      <FloorPlanMap
        floorPlanUrl={floorPlanUrl}
        aps={serverAps}
        grid={grid}
        scalePxPerM={scalePxPerM}
        position={position ? { x: position.x, y: position.y, error: position.error } : null}
      />

      {/* Track toggle FAB */}
      <TouchableOpacity
        style={[styles.fab, trackingActive && styles.fabActive]}
        onPress={() => setTracking(!trackingActive)}
        activeOpacity={0.85}
      >
        <View style={styles.fabInner}>
          <PulseRing active={trackingActive} />
          <View style={[styles.fabDot, { backgroundColor: trackingActive ? C.primary : C.textDim }]} />
        </View>
        <Text style={[styles.fabLabel, { color: trackingActive ? C.primary : C.textDim }]}>
          {trackingActive ? 'TRACKING' : 'START'}
        </Text>
      </TouchableOpacity>

      {/* Bottom info panel */}
      <TouchableOpacity
        activeOpacity={0.9}
        onPress={() => setPanelExpanded(x => !x)}
        style={styles.panel}
      >
        {/* Drag handle */}
        <View style={styles.panelHandle} />

        {/* Position row */}
        <View style={styles.panelRow}>
          {position ? (
            <>
              <View style={styles.coordBlock}>
                <Text style={styles.coordLabel}>X</Text>
                <Text style={styles.coordValue}>{position.x.toFixed(2)}<Text style={styles.coordUnit}>m</Text></Text>
              </View>
              <View style={styles.coordDivider} />
              <View style={styles.coordBlock}>
                <Text style={styles.coordLabel}>Y</Text>
                <Text style={styles.coordValue}>{position.y.toFixed(2)}<Text style={styles.coordUnit}>m</Text></Text>
              </View>
              <View style={{ flex: 1, alignItems: 'flex-end' }}>
                <AccuracyBadge error={position.error} />
              </View>
            </>
          ) : (
            <Text style={styles.noPosition}>
              {!trackingActive ? 'Tap START to begin localization' :
               isScanning      ? 'Scanning Wi-Fi...' :
               serverAps.length === 0 ? 'No APs placed on server' :
               'Waiting for signal...'}
            </Text>
          )}
        </View>

        {/* Expanded info */}
        {panelExpanded && (
          <View style={styles.expandedPanel}>
            <View style={styles.expandedRow}>
              <Text style={styles.expandedLabel}>Visible networks</Text>
              <Text style={styles.expandedValue}>{networks.length}</Text>
            </View>
            <View style={styles.expandedRow}>
              <Text style={styles.expandedLabel}>Matched APs</Text>
              <Text style={styles.expandedValue}>
                {networks.filter(n =>
                  serverAps.some(a => a.bssid.toLowerCase() === n.BSSID.toLowerCase())
                ).length} / {serverAps.length}
              </Text>
            </View>
            {position && (
              <View style={styles.expandedRow}>
                <Text style={styles.expandedLabel}>Method</Text>
                <Text style={styles.expandedValue}>{position.method}</Text>
              </View>
            )}
            {/* Top visible networks */}
            {networks.slice(0, 5).map(n => (
              <View key={n.BSSID} style={styles.netRow}>
                <Text style={styles.netBssid}>{n.BSSID}</Text>
                <Text style={[
                  styles.netLevel,
                  { color: n.level > -60 ? C.green : n.level > -75 ? C.yellow : C.red },
                ]}>{n.level} dBm</Text>
              </View>
            ))}
          </View>
        )}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },

  fab: {
    position: 'absolute', right: 20, top: 20,
    backgroundColor: '#0d1117', borderRadius: 14, borderWidth: 1.5, borderColor: C.border,
    paddingHorizontal: 14, paddingVertical: 12, alignItems: 'center', gap: 4,
    minWidth: 64,
  },
  fabActive: { borderColor: C.primary + '80', backgroundColor: '#0a0f1a' },
  fabInner: { width: 16, height: 16, alignItems: 'center', justifyContent: 'center' },
  fabDot: { width: 10, height: 10, borderRadius: 5 },
  fabLabel: { fontSize: 9, fontFamily: F.mono, letterSpacing: 1.2, fontWeight: '700' },

  panel: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: '#0d1117',
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    borderWidth: 1, borderColor: C.border,
    paddingHorizontal: 20, paddingTop: 10, paddingBottom: 30,
  },
  panelHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: C.border, alignSelf: 'center', marginBottom: 14,
  },
  panelRow: {
    flexDirection: 'row', alignItems: 'center', minHeight: 44,
  },
  coordBlock: { alignItems: 'center', minWidth: 72 },
  coordLabel: { fontSize: 9, color: C.textDim, fontFamily: F.mono, letterSpacing: 1.2, marginBottom: 2 },
  coordValue: { fontSize: 22, fontWeight: '700', color: C.text, fontFamily: F.mono },
  coordUnit: { fontSize: 12, color: C.textDim },
  coordDivider: { width: 1, height: 32, backgroundColor: C.border, marginHorizontal: 14 },
  noPosition: { fontSize: 13, color: C.textDim, flex: 1, textAlign: 'center' },

  expandedPanel: { marginTop: 16, gap: 0 },
  expandedRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border + '40',
  },
  expandedLabel: { fontSize: 12, color: C.textDim },
  expandedValue: { fontSize: 12, color: C.text, fontFamily: F.mono },

  netRow: {
    flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5,
    borderBottomWidth: 1, borderBottomColor: C.border + '20',
  },
  netBssid: { fontSize: 11, color: C.textDim, fontFamily: F.mono },
  netLevel: { fontSize: 11, fontFamily: F.mono, fontWeight: '600' },
});
