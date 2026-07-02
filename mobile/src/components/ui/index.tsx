// Reusable UI primitives for the whole app. RTL-aware, themed, no default RN
// look. Import from '../components/ui'.
import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, font, radius, shadow, spacing, weight } from '../../theme';

// --- Text -------------------------------------------------------------------
export function AppText(props: {
  children: React.ReactNode;
  size?: number;
  color?: string;
  weight?: TextStyle['fontWeight'];
  align?: TextStyle['textAlign'];
  numberOfLines?: number;
  style?: TextStyle | TextStyle[];
}) {
  return (
    <Text
      numberOfLines={props.numberOfLines}
      style={[
        {
          color: props.color ?? colors.textPrimary,
          fontSize: props.size ?? font.body,
          fontWeight: props.weight ?? weight.regular,
          textAlign: props.align ?? 'right',
          writingDirection: 'rtl',
        },
        props.style as TextStyle,
      ]}
    >
      {props.children}
    </Text>
  );
}

// --- Screen wrapper (safe-area + bg) ---------------------------------------
export function Screen({
  children,
  style,
  edges = true,
}: {
  children: React.ReactNode;
  style?: ViewStyle;
  edges?: boolean;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        { flex: 1, backgroundColor: colors.bg, paddingTop: edges ? insets.top : 0 },
        style,
      ]}
    >
      {children}
    </View>
  );
}

// --- Card -------------------------------------------------------------------
export function Card({
  children,
  variant = 'surface',
  style,
}: {
  children: React.ReactNode;
  variant?: 'surface' | 'planned';
  style?: ViewStyle;
}) {
  const planned = variant === 'planned';
  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: planned ? colors.planned : colors.surface,
          borderColor: planned ? colors.plannedBorder : colors.border,
        },
        shadow,
        style,
      ]}
    >
      {children}
    </View>
  );
}

// --- Button -----------------------------------------------------------------
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive';
export function Button({
  title,
  onPress,
  variant = 'primary',
  icon,
  disabled,
  loading,
  style,
}: {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  icon?: keyof typeof Ionicons.glyphMap;
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
}) {
  const bg =
    variant === 'primary' ? colors.accent
    : variant === 'destructive' ? colors.danger
    : variant === 'secondary' ? colors.surfaceAlt
    : 'transparent';
  const fg =
    variant === 'primary' ? colors.onAccent
    : variant === 'destructive' ? '#fff'
    : colors.textPrimary;
  const border = variant === 'ghost' ? colors.border : 'transparent';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, borderColor: border, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <View style={styles.btnRow}>
          {icon ? <Ionicons name={icon} size={18} color={fg} style={{ marginStart: 6 }} /> : null}
          <AppText color={fg} weight={weight.semibold} size={font.title}>
            {title}
          </AppText>
        </View>
      )}
    </Pressable>
  );
}

// --- Input ------------------------------------------------------------------
export function Input(
  props: TextInputProps & {
    iconLeft?: keyof typeof Ionicons.glyphMap;
    onClear?: () => void;
  },
) {
  const { iconLeft, onClear, style, value, ...rest } = props;
  return (
    <View style={styles.inputWrap}>
      {iconLeft ? <Ionicons name={iconLeft} size={18} color={colors.textMuted} /> : null}
      <TextInput
        placeholderTextColor={colors.textMuted}
        style={[styles.input, style]}
        value={value}
        {...rest}
      />
      {onClear && value ? (
        <Pressable onPress={onClear} hitSlop={8}>
          <Ionicons name="close-circle" size={18} color={colors.textMuted} />
        </Pressable>
      ) : null}
    </View>
  );
}

// --- Segmented control ------------------------------------------------------
// Generic two-or-more-way toggle (expense/income, cadence, …). RTL row; the
// selected segment fills with the accent. `tint` recolors the active segment
// (e.g. success green for "income").
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  tint = colors.accent,
}: {
  options: { value: T; label: string; icon?: keyof typeof Ionicons.glyphMap }[];
  value: T;
  onChange: (v: T) => void;
  tint?: string;
}) {
  return (
    <View style={styles.segment}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            onPress={() => onChange(o.value)}
            style={[styles.segmentItem, active && { backgroundColor: tint }]}
          >
            {o.icon ? (
              <Ionicons
                name={o.icon}
                size={16}
                color={active ? colors.onAccent : colors.textSecondary}
                style={{ marginStart: 6 }}
              />
            ) : null}
            <AppText
              weight={active ? weight.semibold : weight.medium}
              color={active ? colors.onAccent : colors.textSecondary}
              size={font.body}
            >
              {o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

// --- Bottom sheet -----------------------------------------------------------
// Modal sheet anchored to the bottom; tap the backdrop to dismiss. Content
// scrolls; respects the bottom safe area so actions never sit under the home
// indicator. `title` + optional close button form the header.
export function BottomSheet({
  visible,
  onClose,
  title,
  children,
}: {
  visible: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.sheetBackdrop} onPress={onClose} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.sheetHandle} />
        {title ? (
          <View style={styles.sheetHeader}>
            <AppText size={font.title} weight={weight.semibold}>
              {title}
            </AppText>
            <Pressable onPress={onClose} hitSlop={10}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </Pressable>
          </View>
        ) : null}
        <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          {children}
        </ScrollView>
      </View>
    </Modal>
  );
}

// --- State views ------------------------------------------------------------
export function LoadingState({ label = 'טוען…' }: { label?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.accent} size="large" />
      <AppText color={colors.textSecondary} style={{ marginTop: spacing.md }}>
        {label}
      </AppText>
    </View>
  );
}

export function EmptyState({
  icon = 'sparkles-outline',
  title,
  subtitle,
  action,
}: {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle?: string;
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View style={styles.center}>
      <View style={styles.emptyIcon}>
        <Ionicons name={icon} size={30} color={colors.accent} />
      </View>
      <AppText size={font.h2} weight={weight.semibold} align="center">
        {title}
      </AppText>
      {subtitle ? (
        <AppText color={colors.textSecondary} align="center" style={{ marginTop: spacing.sm, maxWidth: 280 }}>
          {subtitle}
        </AppText>
      ) : null}
      {action ? (
        <Button title={action.label} onPress={action.onPress} style={{ marginTop: spacing.lg, minWidth: 180 }} />
      ) : null}
    </View>
  );
}

export function ErrorState({
  title = 'לא הצלחנו לטעון את הנתונים',
  subtitle = 'בדוק את החיבור ונסה שוב.',
  onRetry,
}: {
  title?: string;
  subtitle?: string;
  onRetry: () => void;
}) {
  return (
    <View style={styles.center}>
      <View style={[styles.emptyIcon, { backgroundColor: '#3a1f24' }]}>
        <Ionicons name="cloud-offline-outline" size={30} color={colors.danger} />
      </View>
      <AppText size={font.h2} weight={weight.semibold} align="center">
        {title}
      </AppText>
      <AppText color={colors.textSecondary} align="center" style={{ marginTop: spacing.sm, maxWidth: 280 }}>
        {subtitle}
      </AppText>
      <Button title="נסה שוב" icon="refresh" onPress={onRetry} style={{ marginTop: spacing.lg, minWidth: 180 }} />
    </View>
  );
}

// --- Skeleton block ---------------------------------------------------------
export function Skeleton({ height = 16, width, style }: { height?: number; width?: number | string; style?: ViewStyle }) {
  return (
    <View
      style={[
        { height, width: (width as number) ?? '100%', backgroundColor: colors.surfaceAlt, borderRadius: radius.sm },
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.card, borderWidth: 1, padding: spacing.lg },
  segment: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.input,
    padding: 4,
    gap: 4,
  },
  segmentItem: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: radius.input - 4,
  },
  sheetBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '90%',
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.card,
    borderTopRightRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  sheetHandle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
    marginBottom: spacing.md,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  button: {
    borderRadius: radius.input,
    borderWidth: 1,
    paddingVertical: 14,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.input,
    paddingHorizontal: spacing.lg,
  },
  input: { flex: 1, color: colors.textPrimary, fontSize: font.body, paddingVertical: 14, textAlign: 'right' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  emptyIcon: {
    width: 64,
    height: 64,
    borderRadius: radius.pill,
    backgroundColor: colors.accentSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
});
