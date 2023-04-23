import comfy.utils
import folder_paths
import torch

def load_hypernetwork_patch(path, strength):
    sd = comfy.utils.load_torch_file(path, safe_load=True)
    activation_func = sd.get('activation_func', 'linear')
    is_layer_norm = sd.get('is_layer_norm', False)
    use_dropout = sd.get('use_dropout', False)
    activate_output = sd.get('activate_output', False)
    last_layer_dropout = sd.get('last_layer_dropout', False)

    if activation_func != 'linear' or is_layer_norm != False or use_dropout != False or activate_output != False or last_layer_dropout != False:
        print("Unsupported Hypernetwork format, if you report it I might implement it.", path, " ", activation_func, is_layer_norm, use_dropout, activate_output, last_layer_dropout)
        return None

    out = {}

    for d in sd:
        try:
            dim = int(d)
        except:
            continue

        output = []
        for index in [0, 1]:
            attn_weights = sd[dim][index]
            keys = attn_weights.keys()

            linears = filter(lambda a: a.endswith(".weight"), keys)
            linears = sorted(list(map(lambda a: a[:-len(".weight")], linears)))
            layers = []

            for lin_name in linears:
                lin_weight = attn_weights['{}.weight'.format(lin_name)]
                lin_bias = attn_weights['{}.bias'.format(lin_name)]
                layer = torch.nn.Linear(lin_weight.shape[1], lin_weight.shape[0])
                layer.load_state_dict({"weight": lin_weight, "bias": lin_bias})
                layers += [layer]

            output.append(torch.nn.Sequential(*layers))
        out[dim] = torch.nn.ModuleList(output)

    class hypernetwork_patch:
        def __init__(self, hypernet, strength):
            self.hypernet = hypernet
            self.strength = strength
        def __call__(self, current_index, q, k, v):
            dim = k.shape[-1]
            if dim in self.hypernet:
                hn = self.hypernet[dim]
                k = k + hn[0](k) * self.strength
                v = v + hn[1](v) * self.strength

            return q, k, v

        def to(self, device):
            for d in self.hypernet.keys():
                self.hypernet[d] = self.hypernet[d].to(device)
            return self

    return hypernetwork_patch(out, strength)

class HypernetworkLoader:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": { "model": ("MODEL",),
                              "hypernetwork_name": (folder_paths.get_filename_list("hypernetworks"), ),
                              "strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                              }}
    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load_hypernetwork"

    CATEGORY = "_for_testing"

    def load_hypernetwork(self, model, hypernetwork_name, strength):
        hypernetwork_path = folder_paths.get_full_path("hypernetworks", hypernetwork_name)
        model_hypernetwork = model.clone()
        patch = load_hypernetwork_patch(hypernetwork_path, strength)
        if patch is not None:
            model_hypernetwork.set_model_attn1_patch(patch)
            model_hypernetwork.set_model_attn2_patch(patch)
        return (model_hypernetwork,)

NODE_CLASS_MAPPINGS = {
    "HypernetworkLoader": HypernetworkLoader
}
