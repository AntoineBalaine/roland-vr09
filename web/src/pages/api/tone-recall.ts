import type { APIRoute } from "astro";
import { getToneRecall } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getToneRecall(request);
