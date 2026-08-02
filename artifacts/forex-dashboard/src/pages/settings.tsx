import { useEffect } from "react";
import { useGetSettings, useUpdateSettings, getGetSettingsQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Shield, Cpu, Link as LinkIcon, Save, AlertCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const { data: settings, isLoading } = useGetSettings();
  const updateSettings = useUpdateSettings();
  const queryClient = useQueryClient();

  const { register, handleSubmit, reset, formState: { isSubmitting } } = useForm();

  useEffect(() => {
    if (settings) {
      reset({
        riskPerTrade: settings.riskPerTrade,
        maxOpenTrades: settings.maxOpenTrades,
        maxDailyLoss: settings.maxDailyLoss,
        allowedPairs: settings.allowedPairs?.join(", "),
        minConfidence: settings.minConfidence,
        defaultLotSize: settings.defaultLotSize,
        mt5Account: settings.mt5Account,
        mt5Server: settings.mt5Server,
      });
    }
  }, [settings, reset]);

  const onSubmit = async (data: any) => {
    try {
      const payload = {
        ...data,
        riskPerTrade: Number(data.riskPerTrade),
        maxOpenTrades: Number(data.maxOpenTrades),
        maxDailyLoss: Number(data.maxDailyLoss),
        minConfidence: Number(data.minConfidence),
        defaultLotSize: Number(data.defaultLotSize),
        allowedPairs: data.allowedPairs.split(",").map((s: string) => s.trim()).filter(Boolean),
      };
      await updateSettings.mutateAsync({ data: payload });
      toast.success("Configuration updated and deployed to core engine.");
      queryClient.setQueryData(getGetSettingsQueryKey(), (old: any) => ({ ...old, ...payload }));
    } catch (error) {
      toast.error("Failed to commit configuration updates.");
    }
  };

  if (isLoading) {
    return <div className="space-y-6"><Skeleton className="h-10 w-48" /><Skeleton className="h-[500px] w-full" /></div>;
  }

  return (
    <div className="max-w-4xl space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">System Configuration</h1>
          <p className="text-muted-foreground mt-1 text-sm">Critical parameters for the AI engine and risk management.</p>
        </div>
      </div>

      <div className="bg-amber-500/10 border border-amber-500/20 text-amber-500 p-4 rounded-lg flex items-start gap-3 text-sm shadow-[0_0_15px_rgba(245,158,11,0.05)]">
        <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
        <p><strong>Warning:</strong> Changes to risk parameters take effect immediately. Do not adjust maximum open trades or daily loss limits during active high-volatility sessions.</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Risk Management */}
        <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-500" /> Risk Control Matrix
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 grid gap-8 md:grid-cols-2">
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Risk Per Trade (%)</Label>
              <Input type="number" step="0.1" {...register("riskPerTrade")} className="font-mono text-sm bg-background/50 h-10 border-border/50 focus:border-primary" />
            </div>
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Max Daily Loss (%)</Label>
              <Input type="number" step="0.1" {...register("maxDailyLoss")} className="font-mono text-sm bg-background/50 h-10 border-border/50 focus:border-red-500 focus-visible:ring-red-500/20 text-red-400" />
            </div>
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Max Open Concurrency</Label>
              <Input type="number" {...register("maxOpenTrades")} className="font-mono text-sm bg-background/50 h-10 border-border/50 focus:border-primary" />
            </div>
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Allowed Pairs Catalog</Label>
              <Input {...register("allowedPairs")} className="font-mono text-xs tracking-tight bg-background/50 h-10 border-border/50 focus:border-primary" />
            </div>
          </CardContent>
        </Card>

        {/* AI Engine */}
        <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <Cpu className="w-4 h-4 text-primary" /> Model Hyperparameters
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 grid gap-8 md:grid-cols-2">
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Execution Confidence Threshold</Label>
              <Input type="number" step="0.01" {...register("minConfidence")} className="font-mono text-sm bg-background/50 h-10 border-border/50 focus:border-primary" />
            </div>
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Default Lot Sizing</Label>
              <Input type="number" step="0.01" {...register("defaultLotSize")} className="font-mono text-sm bg-background/50 h-10 border-border/50 focus:border-primary" />
            </div>
          </CardContent>
        </Card>

        {/* Integration */}
        <Card className="bg-card/50 backdrop-blur border-border/50 shadow-lg">
          <CardHeader className="border-b border-border/50 pb-4 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
              <LinkIcon className="w-4 h-4 text-blue-500" /> MT5 Integration Endpoint
            </CardTitle>
            <div className="flex items-center gap-2 bg-background/50 px-3 py-1.5 rounded-full border border-border/50">
              <div className={cn("w-2 h-2 rounded-full", settings?.mt5Connected ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)] animate-pulse" : "bg-red-500")} />
              <span className="text-[10px] uppercase font-mono tracking-widest font-bold">
                {settings?.mt5Connected ? "LINK_ACTIVE" : "LINK_OFFLINE"}
              </span>
            </div>
          </CardHeader>
          <CardContent className="p-6 grid gap-8 md:grid-cols-2">
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Account Identifier</Label>
              <Input {...register("mt5Account")} className="font-mono text-sm bg-background/50 h-10 border-border/50 focus:border-primary text-foreground/80" />
            </div>
            <div className="space-y-3">
              <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Server Address</Label>
              <Input {...register("mt5Server")} className="font-mono text-sm bg-background/50 h-10 border-border/50 focus:border-primary text-foreground/80" />
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end pt-4 pb-12">
          <Button type="submit" disabled={isSubmitting} className="h-12 tracking-widest uppercase font-bold text-xs px-10 shadow-lg shadow-primary/20">
            <Save className="w-4 h-4 mr-3" />
            {isSubmitting ? "COMMIT IN PROGRESS..." : "COMMIT CONFIGURATION"}
          </Button>
        </div>
      </form>
    </div>
  );
}
