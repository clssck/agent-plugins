export function Checkout() {
  return (
    <form className="checkout">
      <input type="email" placeholder="Email" />
      <input placeholder="Card number" />
      <button type="submit">Pay</button>
    </form>
  );
}
