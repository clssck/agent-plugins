import Animated, { useAnimatedStyle, useSharedValue, withSpring } from "react-native-reanimated";
import { Pressable, Text } from "react-native";

export function OrderCard({ title }: { title: string }) {
  const scale = useSharedValue(1);
  const style = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  return (
    <Pressable onPressIn={() => (scale.value = withSpring(0.96))} onPressOut={() => (scale.value = withSpring(1))}>
      <Animated.View style={style}><Text>{title}</Text></Animated.View>
    </Pressable>
  );
}
