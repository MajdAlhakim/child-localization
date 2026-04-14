import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, ScrollView,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useStore } from '../store';
import { checkHealth } from '../api/client';
import { C, S, F } from '../theme';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

export default function SettingsScreen() {
  const storeUrl  = useStore(s => s.baseUrl);
  const storeKey  = useStore(s => s.apiKey);
  const setSettings = useStore(s => s.setSettings);
  const isOnline  = useStore(s => s.isOnline);
  const setOnline = useStore(s => s.setOnline);
  const position  = useStore(s => s.position);
  const networks  = useStore(s => s.networks);
  const serverAps = useStore(s => s.serverAps);

  const [baseUrl, setBaseUrl] = useState(storeUrl);
  const [apiKey,  setApiKey]  = useState(storeKey);
  const [testing,  setTesting]  = useState(false);
  const [dirty,    setDirty]    = useState(false);
  const [saved,    setSaved]    = useState(false);

  useEffect(() => {
    setDirty(baseUrl !== storeUrl || apiKey !== storeKey);
    setSaved(false);
  }, [baseUrl, apiKey, storeUrl, storeKey]);

  const save = async () => {
    await AsyncStorage.multiSet([
      ['baseUrl', baseUrl.trim()],
      ['apiKey',  apiKey.trim()],
    ]);
    setSettings(baseUrl.trim(), apiKey.trim());
    setDirty(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const testConnection = async () => {
    setTesting(true);
    try {
      await AsyncStorage.multiSet([
        ['baseUrl', baseUrl.trim()],
        ['apiKey',  apiKey.trim()],
      ]);
      const ok = await checkHealth();
      setOnline(ok);
    } finally {
      setTesting(false);
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Status banner */}
        <View style={styles.statusCard}>
          <View style={[styles.dot, { backgroundColor: isOnline ? C.green : C.red }]} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.statusText, { color: isOnline ? C.green : C.red }]}>
              {isOnline ? 'Server Online' : 'Server Offline'}
            </Text>
            <Text style={styles.statusSub}>{baseUrl}</Text>
          </View>
        </View>

        <Section title="SERVER">
          <View style={styles.fieldWrap}>
            <Text style={styles.fieldLabel}>BASE URL</Text>
            <TextInput
              style={styles.fieldInput}
              value={baseUrl}
              onChangeText={setBaseUrl}
              placeholder="https://trakn.duckdns.org"
              placeholderTextColor={C.textDim + '60'}
              autoCorrect={false}
              autoCapitalize="none"
            />
          </View>
          <View style={[styles.fieldWrap, { borderBottomWidth: 0 }]}>
            <Text style={styles.fieldLabel}>API KEY</Text>
            <TextInput
              style={styles.fieldInput}
              value={apiKey}
              onChangeText={setApiKey}
              placeholder="Enter API key"
              placeholderTextColor={C.textDim + '60'}
              secureTextEntry
              autoCorrect={false}
              autoCapitalize="none"
            />
          </View>
        </Section>

        <View style={styles.buttonRow}>
          <TouchableOpacity
            style={[styles.testBtn, testing && { opacity: 0.6 }]}
            onPress={testConnection}
            disabled={testing}
          >
            {testing
              ? <ActivityIndicator size={16} color={C.primary} />
              : <Text style={styles.testBtnText}>Test</Text>
            }
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.saveBtn, (!dirty || saved) && { opacity: saved ? 0.7 : 0.4 }]}
            onPress={save}
            disabled={!dirty}
          >
            <Text style={styles.saveBtnText}>{saved ? 'Saved!' : 'Save'}</Text>
          </TouchableOpacity>
        </View>

        <Section title="LOCALIZATION">
          <InfoRow label="Algorithm" value="Log-distance + WLS" />
          <InfoRow label="RSSI EMA α" value="0.25" />
          <InfoRow label="Position EMA α" value="0.30" />
          <InfoRow label="Scan interval" value="10 seconds" />
          <InfoRow label="Placed APs" value={`${serverAps.length}`} />
          <InfoRow label="Visible networks" value={`${networks.length}`} />
        </Section>

        {position && (
          <Section title="LAST POSITION">
            <InfoRow label="X" value={`${position.x.toFixed(3)} m`} />
            <InfoRow label="Y" value={`${position.y.toFixed(3)} m`} />
            <InfoRow label="Error est." value={`${position.error.toFixed(2)} m`} />
            <InfoRow label="Method" value={position.method} />
          </Section>
        )}

        <Section title="APP INFO">
          <InfoRow label="Version" value="1.0.0" />
          <InfoRow label="Package" value="qa.qu.trakn.parent.rn" />
          <InfoRow label="Platform" value="Android" />
        </Section>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  scroll: { padding: 16, paddingBottom: 48 },

  statusCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: C.surface, borderRadius: S.lg, borderWidth: 1, borderColor: C.border,
    padding: 14, marginBottom: 16,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { fontSize: 13, fontWeight: '600' },
  statusSub: { fontSize: 11, color: C.textDim, fontFamily: F.mono, marginTop: 2 },

  section: { marginBottom: 16 },
  sectionTitle: {
    fontSize: 10, color: C.textDim, fontFamily: F.mono, letterSpacing: 1.5,
    marginBottom: 8, paddingLeft: 2,
  },
  sectionBody: {
    backgroundColor: C.surface, borderRadius: S.lg, borderWidth: 1, borderColor: C.border,
    overflow: 'hidden',
  },

  fieldWrap: {
    padding: 12, borderBottomWidth: 1, borderBottomColor: C.border + '60',
  },
  fieldLabel: { fontSize: 9, color: C.textDim, fontFamily: F.mono, letterSpacing: 1, marginBottom: 6 },
  fieldInput: { color: C.text, fontSize: 13, fontFamily: F.mono, padding: 0 },

  buttonRow: { flexDirection: 'row', gap: 10, marginBottom: 16 },
  testBtn: {
    flex: 1, padding: 13, borderRadius: S.md,
    backgroundColor: '#1a2030', borderWidth: 1, borderColor: C.primary + '60',
    alignItems: 'center', minHeight: 46,
  },
  testBtnText: { color: C.primary, fontSize: 14, fontWeight: '500' },
  saveBtn: {
    flex: 1, padding: 13, borderRadius: S.md,
    backgroundColor: C.primary, alignItems: 'center',
  },
  saveBtnText: { color: 'white', fontSize: 14, fontWeight: '600' },

  infoRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 14, paddingVertical: 11,
    borderBottomWidth: 1, borderBottomColor: C.border + '40',
  },
  infoLabel: { fontSize: 13, color: C.textDim },
  infoValue: { fontSize: 12, color: C.text, fontFamily: F.mono },
});
