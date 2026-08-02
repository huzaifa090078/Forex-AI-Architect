/**
 * Drizzle ORM schema — AI Forex Trading Bot
 *
 * This schema mirrors the Python SQLAlchemy models in backend/app/db/models.py.
 * The Node.js API server uses this for dev stubs; the Python backend is the
 * production source of truth for all trading logic.
 */

import {
  boolean,
  doublePrecision,
  integer,
  json,
  pgTable,
  text,
  timestamp,
  uuid,
  varchar,
} from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod/v4";

// ─── Users ────────────────────────────────────────────────────────────────────

export const usersTable = pgTable("users", {
  id:             uuid("id").primaryKey().defaultRandom(),
  email:          varchar("email", { length: 255 }).notNull().unique(),
  hashedPassword: varchar("hashed_password", { length: 255 }).notNull(),
  name:           varchar("name", { length: 255 }).notNull(),
  role:           varchar("role", { length: 50 }).notNull().default("viewer"),
  isActive:       boolean("is_active").notNull().default(true),
  createdAt:      timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt:      timestamp("updated_at", { withTimezone: true }),
});

export const insertUserSchema = createInsertSchema(usersTable).omit({ id: true, createdAt: true });
export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = typeof usersTable.$inferSelect;

// ─── Signals ──────────────────────────────────────────────────────────────────

export const signalsTable = pgTable("signals", {
  id:              uuid("id").primaryKey().defaultRandom(),
  userId:          uuid("user_id").notNull().references(() => usersTable.id, { onDelete: "cascade" }),
  pair:            varchar("pair", { length: 20 }).notNull(),
  direction:       varchar("direction", { length: 10 }).notNull(),  // buy | sell
  confidence:      doublePrecision("confidence").notNull(),
  status:          varchar("status", { length: 20 }).notNull().default("pending"),
  entryZoneLow:    doublePrecision("entry_zone_low"),
  entryZoneHigh:   doublePrecision("entry_zone_high"),
  stopLoss:        doublePrecision("stop_loss"),
  takeProfit:      doublePrecision("take_profit"),
  riskRewardRatio: doublePrecision("risk_reward_ratio"),
  smcPattern:      varchar("smc_pattern", { length: 100 }),
  indicators:      json("indicators").$type<string[]>().default([]),
  createdAt:       timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  expiresAt:       timestamp("expires_at", { withTimezone: true }),
});

export const insertSignalSchema = createInsertSchema(signalsTable).omit({ id: true, createdAt: true });
export type InsertSignal = z.infer<typeof insertSignalSchema>;
export type Signal = typeof signalsTable.$inferSelect;

// ─── Trades ───────────────────────────────────────────────────────────────────

export const tradesTable = pgTable("trades", {
  id:              uuid("id").primaryKey().defaultRandom(),
  userId:          uuid("user_id").notNull().references(() => usersTable.id, { onDelete: "cascade" }),
  signalId:        uuid("signal_id").references(() => signalsTable.id, { onDelete: "set null" }),
  pair:            varchar("pair", { length: 20 }).notNull(),
  direction:       varchar("direction", { length: 10 }).notNull(),
  entryPrice:      doublePrecision("entry_price").notNull(),
  stopLoss:        doublePrecision("stop_loss").notNull(),
  takeProfit:      doublePrecision("take_profit").notNull(),
  lotSize:         doublePrecision("lot_size").notNull(),
  status:          varchar("status", { length: 20 }).notNull().default("open"),
  pnl:             doublePrecision("pnl"),
  riskRewardRatio: doublePrecision("risk_reward_ratio"),
  notes:           text("notes"),
  brokerOrderId:   varchar("broker_order_id", { length: 100 }),
  openedAt:        timestamp("opened_at", { withTimezone: true }),
  closedAt:        timestamp("closed_at", { withTimezone: true }),
  createdAt:       timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  updatedAt:       timestamp("updated_at", { withTimezone: true }),
});

export const insertTradeSchema = createInsertSchema(tradesTable).omit({ id: true, createdAt: true });
export type InsertTrade = z.infer<typeof insertTradeSchema>;
export type Trade = typeof tradesTable.$inferSelect;

// ─── Backtests ────────────────────────────────────────────────────────────────

export const backtestsTable = pgTable("backtests", {
  id:             uuid("id").primaryKey().defaultRandom(),
  userId:         uuid("user_id").notNull().references(() => usersTable.id, { onDelete: "cascade" }),
  strategyId:     varchar("strategy_id", { length: 100 }).notNull(),
  pair:           varchar("pair", { length: 20 }).notNull(),
  fromDate:       varchar("from_date", { length: 10 }).notNull(),
  toDate:         varchar("to_date", { length: 10 }).notNull(),
  status:         varchar("status", { length: 20 }).notNull().default("queued"),
  initialBalance: doublePrecision("initial_balance"),
  finalBalance:   doublePrecision("final_balance"),
  totalTrades:    integer("total_trades"),
  winningTrades:  integer("winning_trades"),
  losingTrades:   integer("losing_trades"),
  winRate:        doublePrecision("win_rate"),
  profitFactor:   doublePrecision("profit_factor"),
  maxDrawdown:    doublePrecision("max_drawdown"),
  netPnl:         doublePrecision("net_pnl"),
  sharpeRatio:    doublePrecision("sharpe_ratio"),
  resultDetail:   json("result_detail"),
  createdAt:      timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
  completedAt:    timestamp("completed_at", { withTimezone: true }),
});

export const insertBacktestSchema = createInsertSchema(backtestsTable).omit({ id: true, createdAt: true });
export type InsertBacktest = z.infer<typeof insertBacktestSchema>;
export type Backtest = typeof backtestsTable.$inferSelect;

// ─── News Items ───────────────────────────────────────────────────────────────

export const newsItemsTable = pgTable("news_items", {
  id:          uuid("id").primaryKey().defaultRandom(),
  headline:    text("headline").notNull(),
  source:      varchar("source", { length: 100 }).notNull(),
  impact:      varchar("impact", { length: 20 }).notNull(),
  currency:    varchar("currency", { length: 10 }).notNull(),
  actual:      varchar("actual", { length: 50 }),
  forecast:    varchar("forecast", { length: 50 }),
  previous:    varchar("previous", { length: 50 }),
  publishedAt: timestamp("published_at", { withTimezone: true }).notNull(),
  createdAt:   timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertNewsItemSchema = createInsertSchema(newsItemsTable).omit({ id: true, createdAt: true });
export type InsertNewsItem = z.infer<typeof insertNewsItemSchema>;
export type NewsItem = typeof newsItemsTable.$inferSelect;

// ─── Bot Settings ─────────────────────────────────────────────────────────────

export const botSettingsTable = pgTable("bot_settings", {
  id:                 uuid("id").primaryKey().defaultRandom(),
  userId:             uuid("user_id").notNull().unique().references(() => usersTable.id, { onDelete: "cascade" }),
  riskPerTrade:       doublePrecision("risk_per_trade").notNull().default(1.0),
  maxOpenTrades:      integer("max_open_trades").notNull().default(5),
  maxDailyLoss:       doublePrecision("max_daily_loss").notNull().default(5.0),
  allowedPairs:       json("allowed_pairs").$type<string[]>().default([]),
  tradingEnabled:     boolean("trading_enabled").notNull().default(false),
  newsFilterEnabled:  boolean("news_filter_enabled").notNull().default(true),
  mt5Account:         varchar("mt5_account", { length: 100 }),
  mt5Server:          varchar("mt5_server", { length: 100 }),
  minConfidence:      doublePrecision("min_confidence").notNull().default(0.75),
  defaultLotSize:     doublePrecision("default_lot_size").notNull().default(0.01),
  updatedAt:          timestamp("updated_at", { withTimezone: true }),
});

export const insertBotSettingsSchema = createInsertSchema(botSettingsTable).omit({ id: true });
export type InsertBotSettings = z.infer<typeof insertBotSettingsSchema>;
export type BotSettings = typeof botSettingsTable.$inferSelect;

// ─── System Logs ──────────────────────────────────────────────────────────────

export const systemLogsTable = pgTable("system_logs", {
  id:        uuid("id").primaryKey().defaultRandom(),
  userId:    uuid("user_id").references(() => usersTable.id, { onDelete: "set null" }),
  level:     varchar("level", { length: 20 }).notNull(),
  module:    varchar("module", { length: 100 }).notNull(),
  message:   text("message").notNull(),
  metadata:  json("metadata"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
});

export const insertSystemLogSchema = createInsertSchema(systemLogsTable).omit({ id: true, createdAt: true });
export type InsertSystemLog = z.infer<typeof insertSystemLogSchema>;
export type SystemLog = typeof systemLogsTable.$inferSelect;
