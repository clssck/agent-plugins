import { View, Text } from "react-native";

export function OrderSheet({ orderId }: { orderId: string }) {
  return <View><Text>Order {orderId}</Text></View>;
}
