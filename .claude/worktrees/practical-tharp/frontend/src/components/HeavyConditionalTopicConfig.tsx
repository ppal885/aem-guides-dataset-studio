import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Button } from './ui/button';
import { X, Plus } from 'lucide-react';

interface HeavyConditionalTopicConfigProps {
  recipe: {
    topic_id?: string;
    title?: string;
    target_lines?: number;
    section_count?: number;
    subsections_per_section?: number;
    paragraphs_per_subsection?: number;
    include_tables?: boolean;
    include_codeblocks?: boolean;
    include_notes?: boolean;
    include_examples?: boolean;
    include_xrefs?: boolean;
    include_images?: boolean;
    include_ditaval?: boolean;
    condition_density?: string;
    audience_values?: string[];
    platform_values?: string[];
    otherprops_values?: string[];
    tables_per_n_sections?: number;
    codeblocks_per_n_sections?: number;
    notes_per_n_sections?: number;
    examples_per_n_sections?: number;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function HeavyConditionalTopicConfig({ recipe, onChange }: HeavyConditionalTopicConfigProps) {
  const addValue = (field: 'audience_values' | 'platform_values' | 'otherprops_values') => {
    const values = getValues(field);
    onChange({ ...recipe, [field]: [...values, ''] });
  };

  const getValues = (field: 'audience_values' | 'platform_values' | 'otherprops_values') => {
    const defaults = field === 'audience_values' ? defaultAudiences : field === 'platform_values' ? defaultPlatforms : defaultOtherprops;
    return recipe[field] || defaults;
  };

  const updateValue = (
    field: 'audience_values' | 'platform_values' | 'otherprops_values',
    index: number,
    value: string
  ) => {
    const values = [...getValues(field)];
    values[index] = value;
    onChange({ ...recipe, [field]: values });
  };

  const removeValue = (
    field: 'audience_values' | 'platform_values' | 'otherprops_values',
    index: number
  ) => {
    const values = [...getValues(field)];
    values.splice(index, 1);
    onChange({ ...recipe, [field]: values });
  };

  const defaultAudiences = ['beginner', 'advanced', 'admin', 'developer', 'author', 'reviewer'];
  const defaultPlatforms = ['windows', 'linux', 'mac', 'cloud', 'web'];
  const defaultOtherprops = ['cloud', 'onprem', 'hybrid', 'internal', 'external', 'beta', 'prod', 'staging'];

  return (
    <div className="space-y-4">
      <div>
        <Label>Topic ID</Label>
        <Input
          value={recipe.topic_id || 'heavy_conditional_topic_001'}
          onChange={(e) => onChange({ ...recipe, topic_id: e.target.value })}
          placeholder="heavy_conditional_topic_001"
        />
      </div>

      <div>
        <Label>Title</Label>
        <Input
          value={recipe.title || 'Enterprise Conditional Processing Heavy Topic'}
          onChange={(e) => onChange({ ...recipe, title: e.target.value })}
          placeholder="Topic title"
        />
      </div>

      <div>
        <Label>Target Lines</Label>
        <Input
          type="number"
          value={recipe.target_lines ?? 6000}
          onChange={(e) => onChange({ ...recipe, target_lines: parseInt(e.target.value) || 6000 })}
          min={1000}
          max={50000}
        />
        <p className="text-sm text-gray-500 mt-1">Target line count for the generated topic (1000–50000)</p>
      </div>

      <div>
        <Label>Section Count</Label>
        <Input
          type="number"
          value={recipe.section_count ?? 120}
          onChange={(e) => onChange({ ...recipe, section_count: parseInt(e.target.value) || 120 })}
          min={10}
          max={500}
        />
      </div>

      <div>
        <Label>Subsections per Section</Label>
        <Input
          type="number"
          value={recipe.subsections_per_section ?? 4}
          onChange={(e) => onChange({ ...recipe, subsections_per_section: parseInt(e.target.value) || 4 })}
          min={1}
          max={20}
        />
      </div>

      <div>
        <Label>Paragraphs per Subsection</Label>
        <Input
          type="number"
          value={recipe.paragraphs_per_subsection ?? 6}
          onChange={(e) => onChange({ ...recipe, paragraphs_per_subsection: parseInt(e.target.value) || 6 })}
          min={1}
          max={20}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex items-center space-x-2">
          <Switch
            id="include-tables"
            checked={recipe.include_tables !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_tables: checked })}
          />
          <Label htmlFor="include-tables">Include Tables</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-codeblocks"
            checked={recipe.include_codeblocks !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_codeblocks: checked })}
          />
          <Label htmlFor="include-codeblocks">Include Codeblocks</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-notes"
            checked={recipe.include_notes !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_notes: checked })}
          />
          <Label htmlFor="include-notes">Include Notes</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-examples"
            checked={recipe.include_examples !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_examples: checked })}
          />
          <Label htmlFor="include-examples">Include Examples</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-xrefs"
            checked={recipe.include_xrefs === true}
            onCheckedChange={(checked) => onChange({ ...recipe, include_xrefs: checked })}
          />
          <Label htmlFor="include-xrefs">Include Xrefs</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-images"
            checked={recipe.include_images === true}
            onCheckedChange={(checked) => onChange({ ...recipe, include_images: checked })}
          />
          <Label htmlFor="include-images">Include Images</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id="include-ditaval"
            checked={recipe.include_ditaval !== false}
            onCheckedChange={(checked) => onChange({ ...recipe, include_ditaval: checked })}
          />
          <Label htmlFor="include-ditaval">Include DITAVAL</Label>
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
        <Label>Condition Density</Label>
        <select
          value={recipe.condition_density || 'high'}
          onChange={(e) => onChange({ ...recipe, condition_density: e.target.value })}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="none">None</option>
        </select>
      </div>

      <div>
        <Label>Tables per N Sections</Label>
        <Input
          type="number"
          value={recipe.tables_per_n_sections ?? 2}
          onChange={(e) => onChange({ ...recipe, tables_per_n_sections: parseInt(e.target.value) || 2 })}
          min={1}
          max={20}
        />
        <p className="text-sm text-gray-500 mt-1">Add table every N subsections</p>
      </div>

      <div>
        <Label>Codeblocks per N Sections</Label>
        <Input
          type="number"
          value={recipe.codeblocks_per_n_sections ?? 2}
          onChange={(e) => onChange({ ...recipe, codeblocks_per_n_sections: parseInt(e.target.value) || 2 })}
          min={1}
          max={20}
        />
      </div>

      <div>
        <Label>Notes per N Sections</Label>
        <Input
          type="number"
          value={recipe.notes_per_n_sections ?? 3}
          onChange={(e) => onChange({ ...recipe, notes_per_n_sections: parseInt(e.target.value) || 3 })}
          min={1}
          max={20}
        />
      </div>

      <div>
        <Label>Examples per N Sections</Label>
        <Input
          type="number"
          value={recipe.examples_per_n_sections ?? 3}
          onChange={(e) => onChange({ ...recipe, examples_per_n_sections: parseInt(e.target.value) || 3 })}
          min={1}
          max={20}
        />
      </div>

      <div>
        <Label>Audience Values</Label>
        <div className="space-y-2">
          {getValues('audience_values').map((val, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={val}
                onChange={(e) => updateValue('audience_values', index, e.target.value)}
                placeholder="e.g., admin, developer"
              />
              <Button onClick={() => removeValue('audience_values', index)} variant="ghost" size="sm">
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={() => addValue('audience_values')} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Audience
          </Button>
        </div>
      </div>

      <div>
        <Label>Platform Values</Label>
        <div className="space-y-2">
          {getValues('platform_values').map((val, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={val}
                onChange={(e) => updateValue('platform_values', index, e.target.value)}
                placeholder="e.g., windows, linux"
              />
              <Button onClick={() => removeValue('platform_values', index)} variant="ghost" size="sm">
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={() => addValue('platform_values')} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Platform
          </Button>
        </div>
      </div>

      <div>
        <Label>Otherprops Values</Label>
        <div className="space-y-2">
          {getValues('otherprops_values').map((val, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={val}
                onChange={(e) => updateValue('otherprops_values', index, e.target.value)}
                placeholder="e.g., cloud, onprem"
              />
              <Button onClick={() => removeValue('otherprops_values', index)} variant="ghost" size="sm">
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={() => addValue('otherprops_values')} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Otherprops
          </Button>
        </div>
      </div>
    </div>
  );
}
