import express from "express";
import anthropicMessages from "../controllers/anthropic_controller.ts";

const router = express.Router();

router.post("/v1/messages", anthropicMessages);

export default router;
