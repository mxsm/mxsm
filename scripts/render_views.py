"""Draw a Foshan lion on a drum for each digit of the profile view counter."""

from render_cards import artwork, template


def render_views(count: int) -> str:
    if type(count) is not int or count < 0:
        raise ValueError("View count must be a non-negative integer")

    digits = f"{count:07d}"
    # Embed each distinct pose once, even if the same digit appears on several drums.
    poses = []
    for digit in sorted(set(digits)):
        image = artwork(f"profile-views/{digit}.png")
        poses.append(
            f'<image id="lion-{digit}" x="-64" y="-245" width="128" height="158" '
            f'preserveAspectRatio="xMidYMax meet" xlink:href="{image}"/>'
        )

    # Keep the feet of the drums on the stage when the count outgrows seven places.
    pitch = 875 / len(digits)
    scale = pitch / 125
    drums = []
    for position, digit in enumerate(digits):
        center = 480 + (position - (len(digits) - 1) / 2) * pitch
        drums.append(f'''<g transform="translate({center:.3f} 523) scale({scale:.6f})">
      <use xlink:href="#drum" y="-94"/>
      <use xlink:href="#lion-{digit}"/>
      <text y="-21" stroke="#6b291f" stroke-width="2.4" paint-order="stroke">{digit}</text>
    </g>''')

    return template(
        "profile-views", total=f"{count:,}", stage=artwork("profile-views/stage.jpg"),
        poses="\n    ".join(poses), drums="\n    ".join(drums),
    )
