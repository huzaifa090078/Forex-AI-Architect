import { useEffect } from "react";
import { useGetSettings, useUpdateSettings, getGetSettingsQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Shield, Cpu, Link as LinkIcon, Save, AlertCircle, Newspaper, ToggleLeft, ToggleRight } from "lucide-react";
import { useForm, Controller } from "react-hook-form";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" onClick={() => onChange(!value)}
      className={cn("flex items-center gap-2 px-3 py-1.5 rounded-md text-[10px] font-mono font-bold uppercase tracking-widest border transition-all",
        value
          ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/30"
          : "bg-muted/30 text-muted-foreground border-border/50"
      )}>
      {value ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
      {value ? "ENABLED" : "DISABLED"}
    </button>
  );
}

export default function SettingsPage() {
  const { data: settings, isLoading } = useGetSettings();
  const updateSettings = useUpdateSettings();
  const queryClient    = useQueryClient();

  const { register, handleSubmit, reset, control, formState: { isSubmitting } } = useForm<any>();

  useEffect(() => {
    if (settings) {
      reset({
        riskPerTrade:       settings.riskPerTrade,
        maxOpenTrades:      settings.maxOpenTrades,
        maxDailyLoss:       settings.maxDailyLoss,
        allowedPairs:       settings.allowedPairs?.join(", "),
        minConfidence:      settings.minConfidence,
        defaultLotSize:     settings.defaultLotSize,
        mt5Account:         settings.mt5Account,
        mt5Server:          settings.mt5Server,
        newsFilterEnabled:  settings.newsFilterEnabled ?? true,
        tradingEnabled:     settings.tradingEnabled ?? false,
      });
    }
  }, [settings, reset]);

  const onSubmit = async (data: any) => {
    try {
      const payload = {
        ...data,
        riskPerTrade:    Number(data.riskPerTrade),
        maxOpenTrades:   Number(data.maxOpenTrades),
        maxDailyLoss:    Number(data.maxDailyLoss),
        minConfidence:   Number(data.minConfidence),
        defaultLotSize:  Number(data.defaultLotSize),
        allowedPairs:    data.allowedPairs.split(",").map((s: string) => s.trim()).filter(Boolean),
      };
      await updateSettings.mutateAsync({ data: payload });
      toast.success("Configuration saved and deployed to engine.");
      queryClient.setQueryData(getGetSettingsQueryKey(), (old: any) => ({ ...old, ...payload }));
    } catch {
      toast.error("Failed to save configuration.");
    }
  };

  if (isLoading) {
    return <div className="space-y-6"><Skeleton className="h-10 w-48" /><Skeleton className="h-[500px] w-full" /></div>;
  }

  return (
    <div className="max-w-4xl space-y-6 animate-in fade-in duration-500">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System Configuration</h1>
        <p className="text-muted-foreground text-sm mt-0.5">Risk parameters, AI settings, and news filter configuration</p>
      </div>

      <div className="bg-amber-500/10 border border-amber-500/20 text-amber-500 p-4 rounded-lg flex items-start gap-3 text-sm">
        <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
        <p><strong>Warning:</strong> Changes take effect immediately. Adjust with caution during active trading sessions.</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Risk Management */}
        <Card className="bg-card/50 border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-500" /> Risk Control Matrix
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 grid gap-6 md:grid-cols-2">
            {[
              { label: "Risk Per Trade (%)",   name: "riskPerTrade",  step: "0.1" },
              { label: "Max Daily Loss (%)",   name: "maxDailyLoss",  step: "0.1", cls: "text-red-400" },
              { label: "Max Open Trades",      name: "maxOpenTrades", step: "1" },
            ].map(f => (
              <div key={f.name} className="space-y-2">
                <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{f.label}</Label>
                <Input type="number" step={f.step} {...register(f.name)}
                  className={cn("font-mono text-sm bg-background/50 h-10 border-border/50", f.cls)} />
              </div>
            ))}
            <div className="space-y-2">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Allowed Pairs</Label>
              <Input {...register("allowedPairs")} placeholder="EURUSD, GBPUSD, ..."
                className="font-mono text-xs bg-background/50 h-10 border-border/50" />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Trading Enabled</Label>
              <Controller name="tradingEnabled" control={control}
                render={({ field }) => <Toggle value={!!field.value} onChange={field.onChange} />} />
            </div>
          </CardContent>
        </Card>

        {/* AI Engine */}
        <Card className="bg-card/50 border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Cpu className="w-4 h-4 text-primary" /> AI Engine Parameters
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Confidence Threshold</Label>
              <Input type="number" step="0.01" min="0" max="1" {...register("minConfidence")}
                className="font-mono text-sm bg-background/50 h-10 border-border/50" />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Default Lot Size</Label>
              <Input type="number" step="0.01" {...register("defaultLotSize")}
                className="font-mono text-sm bg-background/50 h-10 border-border/50" />
            </div>
          </CardContent>
        </Card>

        {/* News Filter Settings */}
        <Card className="bg-card/50 border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Newspaper className="w-4 h-4 text-amber-500" /> News Filter (UI Preference)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 space-y-4">
            <div className="space-y-2">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">News Filter Enabled</Label>
              <Controller name="newsFilterEnabled" control={control}
                render={({ field }) => <Toggle value={!!field.value} onChange={field.onChange} />} />
              <p className="text-[10px] text-muted-foreground">
                News filter impact thresholds and timing windows are configured via environment variables
                (NEWS_PAUSE_BEFORE_MINUTES, NEWS_RESUME_AFTER_MINUTES, NEWS_HIGH/MEDIUM/LOW_IMPACT_ENABLED).
                This toggle enables/disables the filter globally.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* MT5 Integration */}
        <Card className="bg-card/50 border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4 flex flex-row items-center justify-between">
            <CardTitle className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <LinkIcon className="w-4 h-4 text-blue-500" /> MT5 Integration Endpoint
            </CardTitle>
            <div className="flex items-center gap-2 bg-background/50 px-3 py-1.5 rounded-full border border-border/50">
              <div className={cn("w-2 h-2 rounded-full", settings?.mt5Connected ? "bg-emerald-500 animate-pulse" : "bg-red-500")} />
              <span className="text-[10px] uppercase font-mono tracking-widest font-bold">
                {settings?.mt5Connected ? "LINK_ACTIVE" : "LINK_OFFLINE"}
              </span>
            </div>
          </CardHeader>
          <CardContent className="p-6 grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Account Identifier</Label>
              <Input {...register("mt5Account")} className="font-mono text-sm bg-background/50 h-10 border-border/50" />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Server Address</Label>
              <Input {...register("mt5Server")} className="font-mono text-sm bg-background/50 h-10 border-border/50" />
            </div>
            <p className="md:col-span-2 text-[10px] text-muted-foreground">
              MT5 credentials (account number, password) are set via environment secrets — never stored or displayed here.
            </p>
          </CardContent>
        </Card>

        <div className="flex justify-end pt-2 pb-10">
          <Button type="submit" disabled={isSubmitting}
            className="h-11 tracking-widest uppercase font-bold text-xs px-10 shadow-lg shadow-primary/20">
            <Save className="w-4 h-4 mr-2" />
            {isSubmitting ? "SAVING..." : "SAVE CONFIGURATION"}
          </Button>
        </div>
      </form>
    </div>
  );
}
