import ezdxf

from utils.dxf_parser import generate_recipe_from_dxf


def test_generate_recipe_from_dxf_with_origin(tmp_path):
    # Create a minimal DXF with a single line from (0, 0) to (1, 0)
    doc = ezdxf.new()
    doc.header['$INSUNITS'] = 4  # millimeters
    msp = doc.modelspace()
    msp.add_line((0, 0), (1, 0))
    path = tmp_path / "sample.dxf"
    doc.saveas(path)

    result = generate_recipe_from_dxf(str(path), origin=(10.0, 5.0), z_height=0.0)

    # Display path should be translated by the origin offset
    display_path = result['display']['paths'][0]
    assert display_path[0] == (10.0, 5.0)
    assert display_path[-1] == (11.0, 5.0)

    # Movement vertices should also be translated
    vertices = result['movement']['vertices']
    assert vertices[0] == (10.0, 5.0, 0.0)
    assert vertices[-1] == (11.0, 5.0, 0.0)

