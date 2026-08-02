import { useAuthRegister } from "@workspace/api-client-react";
import { useLocation, Link } from "wouter";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Hexagon, UserPlus } from "lucide-react";
import { toast } from "sonner";

const registerSchema = z.object({
  name: z.string().min(2),
  email: z.string().email(),
  password: z.string().min(8)
});

export default function RegisterPage() {
  const [, setLocation] = useLocation();
  const registerOp = useAuthRegister();
  
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof registerSchema>>({
    resolver: zodResolver(registerSchema)
  });

  const onSubmit = async (data: z.infer<typeof registerSchema>) => {
    try {
      await registerOp.mutateAsync({ data });
      toast.success("Access granted. Please authenticate.");
      setLocation("/auth/login");
    } catch (e) {
      toast.error("Failed to register operator");
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,_var(--tw-gradient-stops))] from-primary/10 via-background to-background pointer-events-none" />
      
      <div className="w-full max-w-md space-y-8 relative z-10 animate-in fade-in slide-in-from-bottom-8 duration-700">
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="w-16 h-16 rounded-2xl bg-card border border-border/50 flex items-center justify-center mb-4 shadow-[0_0_30px_rgba(20,184,166,0.15)] relative overflow-hidden">
            <div className="absolute inset-0 bg-primary/10 backdrop-blur-xl" />
            <Hexagon className="w-8 h-8 text-primary fill-primary/20 relative z-10" />
          </div>
          <h1 className="text-3xl font-bold tracking-[0.2em]">NEXUS<span className="text-primary">AI</span></h1>
          <p className="text-muted-foreground font-mono text-xs uppercase tracking-widest">Operator Registration</p>
        </div>

        <div className="bg-card/50 backdrop-blur-xl border border-border/50 rounded-2xl p-8 shadow-2xl relative overflow-hidden group">
          <div className="absolute -inset-0.5 bg-gradient-to-tr from-primary/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
          
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 relative z-10">
            <div className="space-y-3">
              <Label className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">Operator Name</Label>
              <Input {...register("name")} className="h-12 bg-background/50 font-mono text-sm focus:border-primary transition-colors border-border/50" placeholder="John Doe" />
              {errors.name && <p className="text-[10px] text-red-500">{errors.name.message}</p>}
            </div>

            <div className="space-y-3">
              <Label className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">Operator ID (Email)</Label>
              <Input type="email" {...register("email")} className="h-12 bg-background/50 font-mono text-sm focus:border-primary transition-colors border-border/50" placeholder="operator@nexus.ai" />
              {errors.email && <p className="text-[10px] text-red-500">{errors.email.message}</p>}
            </div>
            
            <div className="space-y-3">
              <Label className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">Access Key (Password)</Label>
              <Input type="password" {...register("password")} className="h-12 bg-background/50 font-mono text-sm focus:border-primary transition-colors border-border/50" placeholder="••••••••" />
              {errors.password && <p className="text-[10px] text-red-500">{errors.password.message}</p>}
            </div>

            <Button type="submit" disabled={isSubmitting} className="w-full h-12 text-[11px] font-bold uppercase tracking-widest shadow-[0_0_20px_rgba(20,184,166,0.2)] hover:shadow-[0_0_30px_rgba(20,184,166,0.4)] transition-all">
              <UserPlus className="w-4 h-4 mr-2" />
              {isSubmitting ? "PROCESSING..." : "REQUEST ACCESS"}
            </Button>
          </form>

          <div className="mt-8 text-center relative z-10 pt-6 border-t border-border/30">
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-mono">
              Already Registered? <Link href="/auth/login" className="text-primary hover:underline ml-2 font-bold">Initialize Session</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
