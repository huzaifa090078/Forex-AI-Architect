import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(val: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);
}

export function formatNumber(val: number, decimals: number = 2) {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(val);
}

export function formatPercent(val: number, decimals: number = 2) {
  return new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(val);
}

export function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString("en-US", { 
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
  });
}
