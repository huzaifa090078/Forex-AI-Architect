import { Router, type IRouter } from "express";
import healthRouter from "./health";
import stubRouter from "./stubs";

const router: IRouter = Router();

router.use(healthRouter);

// Development stubs — replaced by Python FastAPI in production
router.use(stubRouter);

export default router;
