// Green for anything that points to buying, red for anything that points to selling.
export function leanRow(lean: string) {
  if (["Buy", "good", "pass"].includes(lean)) return "row-buy";
  if (["Sell", "bad", "caution"].includes(lean)) return "row-sell";
  return lean === "Hold off" ? "row-wait" : "";
}
