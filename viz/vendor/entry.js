// Bundle entry: expose three + OrbitControls as window.THREE for the
// single-file template (no module loader exists inside an exported map).
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

window.THREE = Object.assign({}, THREE, { OrbitControls });
