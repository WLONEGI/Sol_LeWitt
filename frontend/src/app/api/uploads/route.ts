import { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const maxDuration = 60;

export async function POST(req: NextRequest) {
    try {
        const authHeader = req.headers.get("authorization") || req.headers.get("Authorization");
        if (!authHeader || !authHeader.toLowerCase().startsWith("bearer ")) {
            return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
        }

        const formData = await req.formData();
        const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

        const response = await fetch(`${BACKEND_URL}/api/files/upload`, {
            method: 'POST',
            headers: {
                Authorization: authHeader,
            },
            body: formData,
        });

        const contentType = response.headers.get('content-type') || 'application/json';
        const responseText = await response.text();
        return new Response(responseText, {
            status: response.status,
            headers: {
                'Content-Type': contentType,
            },
        });
    } catch (error) {
        console.error("[Upload] Failed to proxy upload request:", error);
        return new Response(JSON.stringify({ error: "Upload proxy failed" }), { status: 500 });
    }
}
