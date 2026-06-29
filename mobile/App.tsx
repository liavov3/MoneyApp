// Root: forces Hebrew RTL, provides safe-area context, renders the navigator.
// Auth is config-only (dev token via EXPO_PUBLIC_API_TOKEN) — no login screen.
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { I18nManager } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { RootNavigator } from './src/RootNavigator';

// Hebrew-first: lay everything out right-to-left.
I18nManager.allowRTL(true);
I18nManager.forceRTL(true);

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <RootNavigator />
    </SafeAreaProvider>
  );
}
