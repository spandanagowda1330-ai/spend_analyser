let symbol = "$";

export function setCurrency(newSymbol) {
  symbol = newSymbol || "$";
}

export const money = (n) =>
  n == null
    ? "-"
    : symbol +
      Number(n).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
