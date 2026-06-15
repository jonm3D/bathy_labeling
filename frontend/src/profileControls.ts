export interface ProfileModeBarButton {
  name: string;
  title: string;
  icon: {
    width: number;
    height: number;
    ascent: number;
    descent: number;
    path: string;
  };
  click: () => void;
}

export interface ProfilePlotConfig extends Record<string, unknown> {
  responsive: true;
  scrollZoom: true;
  displaylogo: false;
  modeBarButtonsToRemove: string[];
  modeBarButtonsToAdd: ProfileModeBarButton[];
}

export const PROFILE_DEFAULT_DRAGMODE = "zoom";

const HOME_ICON = {
  width: 512,
  height: 512,
  ascent: 512,
  descent: 0,
  path: "M64 280L256 112L448 280H400V448H112V280H64Z",
};

export function buildProfilePlotConfig(onHome: () => void): ProfilePlotConfig {
  return {
    responsive: true,
    scrollZoom: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["toImage", "autoScale2d", "resetScale2d"],
    modeBarButtonsToAdd: [
      {
        name: "Home",
        title: "Reset view",
        icon: HOME_ICON,
        click: onHome,
      },
    ],
  };
}
