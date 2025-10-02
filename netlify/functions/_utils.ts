import { HandlerEvent, HandlerContext, HandlerResponse } from "@netlify/functions";

export function createHandler(fn: (event: HandlerEvent, context: HandlerContext) => Promise<any>) {
  return async (event: HandlerEvent, context: HandlerContext): Promise<HandlerResponse> => {
    try {
      const result = await fn(event, context);
      return {
        statusCode: 200,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result),
      };
    } catch (err: any) {
      return {
        statusCode: err.statusCode || 500,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ error: err.message }),
      };
    }
  };
}

export function binaryResponse(data: Buffer, contentType: string): HandlerResponse {
  return {
    statusCode: 200,
    headers: { "Content-Type": contentType },
    body: data.toString("base64"),
    isBase64Encoded: true,
  };
}
