import type { APIRoute } from "astro";
import { getData } from "../../lib/library";

export const prerender = false;
export const GET: APIRoute = ({ request }) => getData(request);
