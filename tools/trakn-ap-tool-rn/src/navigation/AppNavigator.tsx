import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { useStore } from '../store';
import { C, F } from '../theme';
import ScanScreen    from '../screens/ScanScreen';
import MapScreen     from '../screens/MapScreen';
import StatusScreen  from '../screens/StatusScreen';
import SettingsScreen from '../screens/SettingsScreen';

const Tab = createBottomTabNavigator();

// Simple icon components (inline SVG-like shapes via View)
function ScanIcon({ focused }: { focused: boolean }) {
  const col = focused ? C.primary : C.textDim;
  return (
    <View style={[icon.wrap]}>
      {[0, 1, 2].map(i => (
        <View
          key={i}
          style={[
            icon.scanBar,
            { height: 6 + i * 4, backgroundColor: col, opacity: focused ? 1 : 0.5 },
          ]}
        />
      ))}
    </View>
  );
}

function MapIcon({ focused }: { focused: boolean }) {
  const col = focused ? C.primary : C.textDim;
  return (
    <View style={[icon.wrap, { position: 'relative' }]}>
      <View style={[icon.mapRect, { borderColor: col }]} />
      <View style={[icon.mapDot, { backgroundColor: col }]} />
    </View>
  );
}

function StatusIcon({ focused }: { focused: boolean }) {
  const col = focused ? C.primary : C.textDim;
  return (
    <View style={icon.wrap}>
      <View style={[icon.circle, { borderColor: col }]}>
        <View style={[icon.circleDot, { backgroundColor: focused ? C.primary : C.textDim }]} />
      </View>
    </View>
  );
}

function SettingsIcon({ focused }: { focused: boolean }) {
  const col = focused ? C.primary : C.textDim;
  return (
    <View style={icon.wrap}>
      <View style={[icon.gear, { borderColor: col }]} />
    </View>
  );
}

const icon = StyleSheet.create({
  wrap: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 2 },
  scanBar: { width: 4, borderRadius: 2 },
  mapRect: { width: 18, height: 16, borderWidth: 1.5, borderRadius: 2 },
  mapDot: { width: 5, height: 5, borderRadius: 2.5, position: 'absolute' },
  circle: { width: 18, height: 18, borderRadius: 9, borderWidth: 1.5 , alignItems: 'center', justifyContent: 'center' },
  circleDot: { width: 6, height: 6, borderRadius: 3 },
  gear: { width: 16, height: 16, borderRadius: 8, borderWidth: 2 },
});

export default function AppNavigator() {
  const isOnline  = useStore(s => s.isOnline);
  const serverAps = useStore(s => s.serverAps);

  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#0a0e16', borderBottomWidth: 1, borderBottomColor: '#1a2030' },
        headerTitleStyle: { color: C.text, fontSize: 15, fontWeight: '600', fontFamily: F.mono },
        headerTintColor: C.primary,
        tabBarStyle: {
          backgroundColor: '#0a0e16',
          borderTopWidth: 1,
          borderTopColor: '#1a2030',
          height: 60,
          paddingBottom: 8,
        },
        tabBarActiveTintColor: C.primary,
        tabBarInactiveTintColor: C.textDim,
        tabBarLabelStyle: { fontSize: 10, fontFamily: F.mono, letterSpacing: 0.5 },
      }}
    >
      <Tab.Screen
        name="Scan"
        component={ScanScreen}
        options={{
          title: 'TRAKN AP Tool',
          tabBarLabel: 'Scan',
          tabBarIcon: ({ focused }) => <ScanIcon focused={focused} />,
          headerRight: () => (
            <View style={{ flexDirection: 'row', alignItems: 'center', marginRight: 14, gap: 6 }}>
              <View style={[{ width: 7, height: 7, borderRadius: 3.5, backgroundColor: isOnline ? C.green : C.red }]} />
              <Text style={{ fontSize: 11, color: isOnline ? C.green : C.red, fontFamily: F.mono }}>
                {isOnline ? 'online' : 'offline'}
              </Text>
            </View>
          ),
        }}
      />
      <Tab.Screen
        name="Map"
        component={MapScreen}
        options={{
          title: 'Place APs',
          tabBarLabel: 'Map',
          tabBarIcon: ({ focused }) => <MapIcon focused={focused} />,
        }}
      />
      <Tab.Screen
        name="Status"
        component={StatusScreen}
        options={{
          title: 'Status',
          tabBarLabel: 'Status',
          tabBarIcon: ({ focused }) => <StatusIcon focused={focused} />,
          tabBarBadge: serverAps.length > 0 ? serverAps.length : undefined,
          tabBarBadgeStyle: { backgroundColor: C.primary, fontSize: 10 },
        }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          title: 'Settings',
          tabBarLabel: 'Settings',
          tabBarIcon: ({ focused }) => <SettingsIcon focused={focused} />,
        }}
      />
    </Tab.Navigator>
  );
}
