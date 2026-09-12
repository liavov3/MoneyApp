import React, { createContext, useContext, useEffect, useId } from 'react';
import { Keyboard, StyleSheet, View } from 'react-native';

// Each native modal gets the same cover inside its own presentation surface.
// Keeping its children mounted preserves unsaved forms during reconnection.
export const ConnectionContext = createContext({
  locked: false,
  renderGate: (): React.ReactNode => null,
  topCover: null as string | null,
  registerCover: (_id: string): (() => void) => () => {},
});
export const useConnectionLocked = () => useContext(ConnectionContext).locked;

export function ConnectionGuard({ children, modal = false, visible = true }: { children: React.ReactNode; modal?: boolean; visible?: boolean }) {
  const { locked, renderGate, registerCover, topCover } = useContext(ConnectionContext);
  const id = useId();
  useEffect(() => { if (modal && visible) return registerCover(id); }, [modal, visible, registerCover, id]);
  useEffect(() => { if (locked) Keyboard.dismiss(); }, [locked]);
  const showGate = locked && (modal ? topCover === id : topCover === null);
  return (
    <View style={styles.fill}>
      <View style={[styles.fill, locked && styles.hidden]} pointerEvents={locked ? 'none' : 'auto'}
        accessibilityElementsHidden={locked} importantForAccessibility={locked ? 'no-hide-descendants' : 'auto'}
        aria-hidden={locked}>
        {children}
      </View>
      {showGate ? <View style={StyleSheet.absoluteFill}>{renderGate()}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({ fill: { flex: 1 }, hidden: { opacity: 0 } });
