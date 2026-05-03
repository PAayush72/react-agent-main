# ui/colors.py — Neural Terminal color scheme and Rich theme

from rich.theme import Theme

C = {
    "cyan":        "#00CED1",
    "cyan_bright": "#00FFFF",
    "cyan_dim":    "#008B8B",
    "green":       "#00D700",
    "green_dim":   "#006400",
    "purple":      "#AF87FF",
    "purple_dim":  "#6A5ACD",
    "amber":       "#FFAF00",
    "red":         "#FF5555",
    "white":       "#E8E8E8",
    "white_dim":   "#AAAAAA",
    "gray":        "#626262",
    "gray_dark":   "#3A3A3A",
    "gray_light":  "#888888",
    "blue":        "#5C7CFA",
    "yellow":      "#FFD700",
    "bg_user":     "#0D1B2A",
    "bg_answer":   "#0A1A0A",
    "separator":   "#2A2A2A",
}

THEME = Theme({
    "neural.cyan":       C["cyan"],
    "neural.cyan_b":     f"bold {C['cyan']}",
    "neural.green":      C["green"],
    "neural.green_b":    f"bold {C['green']}",
    "neural.purple":     f"italic {C['purple']}",
    "neural.amber":      C["amber"],
    "neural.amber_b":    f"bold {C['amber']}",
    "neural.red":        f"bold {C['red']}",
    "neural.white":      C["white"],
    "neural.white_b":    f"bold {C['white']}",
    "neural.gray":       f"dim {C['gray']}",
    "neural.gray_l":     C["gray_light"],
    "neural.yellow":     C["yellow"],
    "neural.blue":       C["blue"],
    "neural.sep":        C["separator"],
    "neural.step":       f"dim {C['gray']}",
    "neural.tool":       f"bold {C['cyan']}",
    "neural.arg_key":    f"dim {C['gray_light']}",
    "neural.arg_val":    C["white"],
    "neural.thought":    f"italic {C['purple']}",
    "neural.obs":        f"dim {C['white_dim']}",
})
