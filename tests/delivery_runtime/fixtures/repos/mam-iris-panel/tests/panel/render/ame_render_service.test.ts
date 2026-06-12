import { diagnoseMediaOffline } from "../../../src/panel/render/ame_render_service";

describe("ame_render_service", () => {
  it("flags media offline renders", async () => {
    await expect(diagnoseMediaOffline("1780297464807")).resolves.toHaveLength(1);
  });
});
