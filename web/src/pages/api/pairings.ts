import type { APIRoute } from "astro";
import { getPairings, postPairing } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getPairings(request);
export const POST: APIRoute = ({ request }) => postPairing(request);
