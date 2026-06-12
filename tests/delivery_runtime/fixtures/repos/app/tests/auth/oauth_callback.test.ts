import { persistOAuthTokens } from "../../../src/auth/oauth_callback";

describe("oauth_callback", () => {
  it("persists tokens", async () => {
    await expect(persistOAuthTokens({ access: "x" })).resolves.toBeUndefined();
  });
});
