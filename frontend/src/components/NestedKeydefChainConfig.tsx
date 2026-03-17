import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Button } from './ui/button';
import { X, Plus } from 'lucide-react';

interface NestedKeydefChainConfigProps {
  recipe: {
    root_map_name?: string;
    intermediate_map_name?: string;
    keyword_topic_name?: string;
    consumer_topic_name?: string;
    root_map_title?: string;
    intermediate_map_title?: string;
    keyword_topic_title?: string;
    consumer_topic_title?: string;
    root_to_intermediate_key?: string;
    direct_intermediate_key_name?: string;
    nested_keyword_file_key_name?: string;
    nested_keyword_id?: string;
    consumer_keyrefs?: string[];
    include_direct_key_in_root_map?: boolean;
    include_direct_key_in_intermediate_map?: boolean;
    include_nested_keyword_topic?: boolean;
    include_workaround_notes?: boolean;
    generation_mode?: string;
    add_negative_variant?: boolean;
    add_workaround_variant?: boolean;
    id_prefix?: string;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function NestedKeydefChainConfig({ recipe, onChange }: NestedKeydefChainConfigProps) {
  const consumerKeyrefs = recipe.consumer_keyrefs || ['productName', 'versionString'];

  const addKeyref = () => {
    onChange({ ...recipe, consumer_keyrefs: [...consumerKeyrefs, ''] });
  };

  const updateKeyref = (index: number, value: string) => {
    const updated = [...consumerKeyrefs];
    updated[index] = value;
    onChange({ ...recipe, consumer_keyrefs: updated });
  };

  const removeKeyref = (index: number) => {
    const updated = consumerKeyrefs.filter((_, i) => i !== index);
    onChange({ ...recipe, consumer_keyrefs: updated });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Minimal repro for nested keydef chain: Map A → Map B → Topic C. Reproduces Web Editor bug where nested keys
        are unresolved when Map A is context but resolve when Map B is root. DITA-OT publishes correctly.
      </p>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Root Map Name</Label>
          <Input
            value={recipe.root_map_name || 'map_a.ditamap'}
            onChange={(e) => onChange({ ...recipe, root_map_name: e.target.value })}
            placeholder="map_a.ditamap"
          />
        </div>
        <div>
          <Label>Intermediate Map Name</Label>
          <Input
            value={recipe.intermediate_map_name || 'map_b.ditamap'}
            onChange={(e) => onChange({ ...recipe, intermediate_map_name: e.target.value })}
            placeholder="map_b.ditamap"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Keyword Topic Name</Label>
          <Input
            value={recipe.keyword_topic_name || 'topic_c_keywords.dita'}
            onChange={(e) => onChange({ ...recipe, keyword_topic_name: e.target.value })}
            placeholder="topic_c_keywords.dita"
          />
        </div>
        <div>
          <Label>Consumer Topic Name</Label>
          <Input
            value={recipe.consumer_topic_name || 'topic_d_consumer.dita'}
            onChange={(e) => onChange({ ...recipe, consumer_topic_name: e.target.value })}
            placeholder="topic_d_consumer.dita"
          />
        </div>
      </div>

      <div>
        <Label>Root Map Title</Label>
        <Input
          value={recipe.root_map_title || 'Outer Context Map'}
          onChange={(e) => onChange({ ...recipe, root_map_title: e.target.value })}
        />
      </div>

      <div>
        <Label>Intermediate Map Title</Label>
        <Input
          value={recipe.intermediate_map_title || 'Static Key Map'}
          onChange={(e) => onChange({ ...recipe, intermediate_map_title: e.target.value })}
        />
      </div>

      <div>
        <Label>Root-to-Intermediate Key</Label>
        <Input
          value={recipe.root_to_intermediate_key || 'staticKeyMap'}
          onChange={(e) => onChange({ ...recipe, root_to_intermediate_key: e.target.value })}
          placeholder="staticKeyMap"
        />
        <p className="text-xs text-slate-500 mt-1">Key in Map A pointing to Map B</p>
      </div>

      <div>
        <Label>Direct Key in Map B</Label>
        <Input
          value={recipe.direct_intermediate_key_name || 'productName'}
          onChange={(e) => onChange({ ...recipe, direct_intermediate_key_name: e.target.value })}
          placeholder="productName"
        />
      </div>

      <div>
        <Label>Nested Keyword File Key</Label>
        <Input
          value={recipe.nested_keyword_file_key_name || 'keywordFile'}
          onChange={(e) => onChange({ ...recipe, nested_keyword_file_key_name: e.target.value })}
          placeholder="keywordFile"
        />
      </div>

      <div>
        <Label>Keyword ID in Topic C</Label>
        <Input
          value={recipe.nested_keyword_id || 'versionString'}
          onChange={(e) => onChange({ ...recipe, nested_keyword_id: e.target.value })}
          placeholder="versionString"
        />
      </div>

      <div>
        <Label>Consumer Keyrefs</Label>
        <div className="space-y-2">
          {consumerKeyrefs.map((kr, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={kr}
                onChange={(e) => updateKeyref(index, e.target.value)}
                placeholder="e.g., productName"
              />
              <Button onClick={() => removeKeyref(index)} variant="ghost" size="sm">
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={addKeyref} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Keyref
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex items-center space-x-2">
          <Switch
            id="include-direct-root"
            checked={recipe.include_direct_key_in_root_map !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_direct_key_in_root_map: checked })}
          />
          <Label htmlFor="include-direct-root">Include Direct Key in Root Map</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-direct-intermediate"
            checked={recipe.include_direct_key_in_intermediate_map !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_direct_key_in_intermediate_map: checked })}
          />
          <Label htmlFor="include-direct-intermediate">Include Direct Key in Intermediate Map</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-nested-keyword"
            checked={recipe.include_nested_keyword_topic !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_nested_keyword_topic: checked })}
          />
          <Label htmlFor="include-nested-keyword">Include Nested Keyword Topic</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-workaround"
            checked={recipe.include_workaround_notes !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_workaround_notes: checked })}
          />
          <Label htmlFor="include-workaround">Include Workaround Notes</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="pretty-print"
            checked={recipe.pretty_print !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
          />
          <Label htmlFor="pretty-print">Pretty Print XML</Label>
        </div>
      </div>

      <div>
        <Label>Generation Mode</Label>
        <select
          value={recipe.generation_mode || 'minimal_repro'}
          onChange={(e) => onChange({ ...recipe, generation_mode: e.target.value })}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="minimal_repro">Minimal Repro</option>
          <option value="extended_repro">Extended Repro</option>
        </select>
      </div>
    </div>
  );
}
