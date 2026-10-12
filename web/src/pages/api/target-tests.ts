import type { APIRoute } from "astro";
import { getTargetTests, postTargetTest } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getTargetTests(request);
export const POST: APIRoute = ({ request }) => postTargetTest(request);
