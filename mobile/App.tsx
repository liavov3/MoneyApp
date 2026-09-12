// Root: forces Hebrew RTL, provides safe-area context, renders the navigator.
// The connection gate restores a runtime credential from secure device storage.
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { I18nManager } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { SessionGate } from './src/SessionGate';

// Hebrew-first: lay everything out right-to-left.
I18nManager.allowRTL(true);
I18nManager.forceRTL(true);

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <SessionGate />
    </SafeAreaProvider>
  );
}
