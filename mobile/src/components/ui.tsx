// Small shared primitives (ponytail: one Card with a tint prop, one Button with
// variants — not a component per purpose). RTL-aware text defaults.
import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';

import { colors, font, radius, spacing } from '../theme';

export function Card(props: {
  children: React.ReactNode;
  planned?: boolean;
  style?: ViewStyle;
}) {
  return (
    <View
      style={[
        styles.card,
        { backgroundColor: props.planned ? colors.planned : colors.surface },
        props.style,
      ]}
    >
      {props.children}
    </View>
  );
}

export function AppText(props: {
  children: React.ReactNode;
  size?: number;
  color?: string;
  weight?: TextStyle['fontWeight'];
  style?: TextStyle;
}) {
  return (
    <Text
      style={[
        {
          color: props.color ?? colors.textPrimary,
          fontSize: props.size ?? font.body,
          fontWeight: props.weight,
          textAlign: 'right',
          writingDirection: 'rtl',
        },
        props.style,
      ]}
    >
      {props.children}
    </Text>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <AppText size={font.caption} color={colors.textSecondary} style={{ marginBottom: spacing.sm }}>
      {children}
    </AppText>
  );
}

export function Button(props: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
}) {
  const primary = (props.variant ?? 'primary') === 'primary';
  return (
    <Pressable
      onPress={props.onPress}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor: primary ? colors.accent : 'transparent',
          borderColor: primary ? colors.accent : colors.border,
          opacity: pressed ? 0.85 : 1,
        },
      ]}
    >
      <AppText
        color={primary ? '#0B1320' : colors.textPrimary}
        weight="600"
        size={font.title}
        style={{ textAlign: 'center' }}
      >
        {props.title}
      </AppText>
    </Pressable>
  );
}

export function Loading({ label }: { label?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.accent} size="large" />
      {label ? (
        <AppText color={colors.textSecondary} style={{ marginTop: spacing.md }}>
          {label}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  button: {
    borderRadius: radius.input,
    borderWidth: 1,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
});
