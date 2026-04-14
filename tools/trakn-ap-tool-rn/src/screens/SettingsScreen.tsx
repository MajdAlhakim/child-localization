import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, ActivityIndicator, ScrollView, Switch,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useStore } from '../store';
import { checkHealth } from '../api/client';
import { C, S, F } from '../theme';
import { useToastState } from '../hooks/useToast';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

function Field({
  label, value, onChange, placeholder, secure = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  secure?: boolean;
}) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.fieldInput}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={C.textDim + '80'}
        secureTextEntry={secure}
        autoCorrect={false}
        autoCapitalize="none"
      />
    </View>
  );
}

export default function SettingsScreen() {
  const storeSettings = useStore(s => ({ baseUrl: s.baseUrl, apiKey: s.apiKey }));
  const setSettings   = useStore(s => s.setSettings);
  const isOnline      = useStore(s => s.isOnline);
  const setOnline     = useStore(s => s.setOnline);

  const [baseUrl, setBaseUrl] = useState(storeSettings.baseUrl);
  const [apiKey,  setApiKey]  = useState(storeSettings.apiKey);
  const [testing,  setTesting]  = useState(false);
  const [dirty,    setDirty]    = useState(false);
  const { toasts, toast } = useToastState();

  useEffect(() => {
    setDirty(baseUrl !== storeSettings.baseUrl || apiKey !== storeSettings.apiKey);
  }, [baseUrl, apiKey, storeSettings]);

  const save = async () => {
    await AsyncStorage.multiSet([
      ['baseUrl', baseUrl.trim()],
      ['apiKey',  apiKey.trim()],
    ]);
    setSettings(baseUrl.trim(), apiKey.trim());
    toast('Settings saved', 'success');
    setDirty(false);
  };

  const testConnection = async () => {
    setTesting(true);
    try {
      // Temporarily write to AsyncStorage for the health check to pick up
      await AsyncStorage.multiSet([
        ['baseUrl', baseUrl.trim()],
        ['apiKey',  apiKey.trim()],
      ]);
      const ok = await checkHealth();
      setOnline(ok);
      toast(ok ? 'Connection successful!' : 'Server unreachable', ok ? 'success' : 'error');
    } finally {
      setTesting(false);
    }
  };

  return (
    <View style={styles.root}>
      {/* Toast overlay */}
      <View style={styles.toastWrap} pointerEvents="none">
        {toasts.map(t => (
          <View
            key={t.id}
            style={[
              styles.toast,
              t.type === 'success' && styles.toastSuccess,
              t.type === 'error'   && styles.toastError,
            ]}
          >
            <Text style={styles.toastText}>{t.msg}</Text>
          </View>
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Connection status */}
        <View style={styles.statusCard}>
          <View style={[styles.dot, { backgroundColor: isOnline ? C.green : C.red }]} />
          <Text style={[styles.statusText, { color: isOnline ? C.green : C.red }]}>
            {isOnline ? 'Server Online' : 'Server Offline'}
          </Text>
        </View>

        <Section title="SERVER">
          <Field
            label="BASE URL"
            value={baseUrl}
            onChange={setBaseUrl}
            placeholder="https://trakn.duckdns.org"
          />
          <Field
            label="API KEY"
            value={apiKey}
            onChange={setApiKey}
            placeholder="Enter API key"
            secure
          />
        </Section>

        <View style={styles.buttonRow}>
          <TouchableOpacity
            style={[styles.testBtn, testing && { opacity: 0.6 }]}
            onPress={testConnection}
            disabled={testing}
          >
            {testing
              ? <ActivityIndicator size={16} color={C.primary} />
              : <Text style={styles.testBtnText}>Test Connection</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.saveBtn, !dirty && { opacity: 0.4 }]}
            onPress={save}
            disabled={!dirty}
          >
            <Text style={styles.saveBtnText}>Save</Text>
          </TouchableOpacity>
        </View>

        <Section title="SCAN SETTINGS">
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Scan interval</Text>
            <Text style={styles.infoValue}>15 seconds</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Permission</Text>
            <Text style={styles.infoValue}>ACCESS_FINE_LOCATION</Text>
          </View>
        </Section>

        <Section title="RTT RANGING">
          <View style={styles.rttPlaceholder}>
            <Text style={styles.rttTitle}>Wi-Fi RTT (802.11mc) — Placeholder</Text>
            <Text style={styles.rttDesc}>
              Round-trip time ranging requires native Android code (WifiRttManager).
              This feature is not yet available in the React Native implementation.
              The app currently uses RSSI-based log-distance path loss for positioning.
            </Text>
          </View>
        </Section>

        <Section title="APP INFO">
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Version</Text>
            <Text style={styles.infoValue}>1.0.0</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Package</Text>
            <Text style={styles.infoValue}>qa.qu.trakn.aptool.rn</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Platform</Text>
            <Text style={styles.infoValue}>Android</Text>
          </View>
        </Section>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  scroll: { padding: 16, paddingBottom: 48 },

  toastWrap: { position: 'absolute', top: 12, left: 16, right: 16, zIndex: 100, gap: 6 },
  toast: {
    backgroundColor: '#1a2030', borderRadius: 10, borderWidth: 1, borderColor: C.border,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  toastSuccess: { borderColor: C.green + '60', backgroundColor: '#0a1f14' },
  toastError:   { borderColor: C.red + '60',   backgroundColor: '#1f0a0a' },
  toastText:    { color: C.text, fontSize: 13 },

  statusCard: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#0d1117', borderRadius: S.lg, borderWidth: 1, borderColor: C.border,
    padding: 14, marginBottom: 16,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { fontSize: 13, fontWeight: '500' },

  section: { marginBottom: 16 },
  sectionTitle: {
    fontSize: 10, color: C.textDim, fontFamily: F.mono, letterSpacing: 1.5,
    marginBottom: 8, paddingLeft: 2,
  },
  sectionBody: {
    backgroundColor: '#0d1117', borderRadius: S.lg, borderWidth: 1, borderColor: C.border,
    overflow: 'hidden',
  },

  fieldWrap: { padding: 12, borderBottomWidth: 1, borderBottomColor: C.border + '60' },
  fieldLabel: { fontSize: 9, color: C.textDim, fontFamily: F.mono, letterSpacing: 1, marginBottom: 6 },
  fieldInput: {
    color: C.text, fontSize: 13, fontFamily: F.mono,
    padding: 0, // iOS removes default input padding
  },

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
    paddingHorizontal: 14, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: C.border + '40',
  },
  infoLabel: { fontSize: 13, color: C.textDim },
  infoValue: { fontSize: 12, color: C.text, fontFamily: F.mono },

  rttPlaceholder: { padding: 14 },
  rttTitle: { fontSize: 12, color: C.yellow, fontWeight: '600', marginBottom: 8 },
  rttDesc: { fontSize: 12, color: C.textDim, lineHeight: 18 },
});
