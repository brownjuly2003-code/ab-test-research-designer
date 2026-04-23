import type { ReactNode } from "react";

const Box = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
const Leaf = () => null;

export const ResponsiveContainer = Box;
export const ComposedChart = Box;
export const LineChart = Box;
export const BarChart = Box;
export const ScatterChart = Box;
export const Area = Leaf;
export const Line = Leaf;
export const Bar = Leaf;
export const Scatter = Leaf;
export const ReferenceLine = Leaf;
export const ReferenceArea = Leaf;
export const CartesianGrid = Leaf;
export const XAxis = Leaf;
export const YAxis = Leaf;
export const Tooltip = Leaf;
export const Legend = Leaf;
export const Cell = Leaf;
export const Customized = Leaf;
