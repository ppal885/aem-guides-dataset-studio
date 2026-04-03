import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Button } from './ui/button';
import { X, Plus } from 'lucide-react';

interface ConditionalContentConfigProps {
  recipe: {
    topic_count?: number;
    audiences?: string[];
    platforms?: string[];
    products?: string[];
    generate_ditaval?: boolean;
    ditaval_profiles?: string[];
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function ConditionalContentConfig({ recipe, onChange }: ConditionalContentConfigProps) {
  const addValue = (field: 'audiences' | 'platforms' | 'products') => {
    const values = recipe[field] || [];
    onChange({ ...recipe, [field]: [...values, ''] });
  };

  const updateValue = (field: 'audiences' | 'platforms' | 'products', index: number, value: string) => {
    const values = [...(recipe[field] || [])];
    values[index] = value;
    onChange({ ...recipe, [field]: values });
  };

  const removeValue = (field: 'audiences' | 'platforms' | 'products', index: number) => {
    const values = [...(recipe[field] || [])];
    values.splice(index, 1);
    onChange({ ...recipe, [field]: values });
  };

  return (
    <div className="space-y-4">
      <div>
        <Label>Topic Count</Label>
        <Input
          type="number"
          value={recipe.topic_count || 50}
          onChange={(e) => onChange({ ...recipe, topic_count: parseInt(e.target.value) || 50 })}
          min={10}
          max={5000}
        />
      </div>

      <div>
        <Label>Audiences</Label>
        <div className="space-y-2">
          {(recipe.audiences || ['admin', 'user', 'developer']).map((audience, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={audience}
                onChange={(e) => updateValue('audiences', index, e.target.value)}
                placeholder="e.g., admin, user"
              />
              <Button
                onClick={() => removeValue('audiences', index)}
                variant="ghost"
                size="sm"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={() => addValue('audiences')} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Audience
          </Button>
        </div>
      </div>

      <div>
        <Label>Platforms</Label>
        <div className="space-y-2">
          {(recipe.platforms || ['windows', 'mac', 'linux']).map((platform, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={platform}
                onChange={(e) => updateValue('platforms', index, e.target.value)}
                placeholder="e.g., windows, mac"
              />
              <Button
                onClick={() => removeValue('platforms', index)}
                variant="ghost"
                size="sm"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={() => addValue('platforms')} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Platform
          </Button>
        </div>
      </div>

      <div>
        <Label>Products</Label>
        <div className="space-y-2">
          {(recipe.products || ['product-a', 'product-b']).map((product, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={product}
                onChange={(e) => updateValue('products', index, e.target.value)}
                placeholder="e.g., product-a"
              />
              <Button
                onClick={() => removeValue('products', index)}
                variant="ghost"
                size="sm"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={() => addValue('products')} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Product
          </Button>
        </div>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="generate-ditaval"
          checked={recipe.generate_ditaval !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, generate_ditaval: checked })}
        />
        <Label htmlFor="generate-ditaval">Generate DITAVAL Files</Label>
      </div>

      {recipe.generate_ditaval !== false && (
        <div>
          <Label>DITAVAL Profiles</Label>
          <div className="space-y-2">
            {(recipe.ditaval_profiles || ['admin-windows', 'user-all']).map((profile, index) => (
              <div key={index} className="flex gap-2">
                <Input
                  value={profile}
                  onChange={(e) => {
                    const profiles = [...(recipe.ditaval_profiles || [])];
                    profiles[index] = e.target.value;
                    onChange({ ...recipe, ditaval_profiles: profiles });
                  }}
                  placeholder="e.g., admin-windows"
                />
                <Button
                  onClick={() => {
                    const profiles = [...(recipe.ditaval_profiles || [])];
                    profiles.splice(index, 1);
                    onChange({ ...recipe, ditaval_profiles: profiles });
                  }}
                  variant="ghost"
                  size="sm"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <Button
              onClick={() => {
                const profiles = [...(recipe.ditaval_profiles || [])];
                onChange({ ...recipe, ditaval_profiles: [...profiles, ''] });
              }}
              variant="outline"
              size="sm"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Profile
            </Button>
          </div>
        </div>
      )}

      <div className="flex items-center space-x-2">
        <Switch
          id="include-map"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_map: checked })}
        />
        <Label htmlFor="include-map">Include Map</Label>
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
  );
}
