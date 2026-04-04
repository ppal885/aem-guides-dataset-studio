import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface BulkDitaMapTopicsConfigProps {
  recipe: {
    topic_count?: number;
    include_readme?: boolean;
    pretty_print?: boolean;
    include_local_dtd_stubs?: boolean;
  };
  onChange: (recipe: Record<string, unknown>) => void;
}

export function BulkDitaMapTopicsConfig({ recipe, onChange }: BulkDitaMapTopicsConfigProps) {
  const stubsOn = recipe.include_local_dtd_stubs !== false;

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Generates simple DITA topics under <code className="rounded bg-slate-100 px-1">topics/</code> and one root
        map listing every topicref with <code className="rounded bg-slate-100 px-1">navtitle</code> — same layout as
        the standalone <code className="rounded bg-slate-100 px-1">generate_dita_20k_dataset.py</code> script.
      </p>
      <p className="text-sm text-slate-600">
        By default, minimal DITA DTD stubs are included under{' '}
        <code className="rounded bg-slate-100 px-1">technicalContent/dtd/</code> so topic files under{' '}
        <code className="rounded bg-slate-100 px-1">topics/</code> resolve correctly in Oxygen or AEM validation. Turn
        this off only for catalog-only flows that expect stubs at the dataset root.
      </p>
      <div>
        <Label>Topic count</Label>
        <Input
          type="number"
          value={recipe.topic_count ?? 20000}
          onChange={(e) =>
            onChange({ ...recipe, topic_count: Math.max(1, parseInt(e.target.value, 10) || 1) })
          }
          min={1}
          max={25000}
        />
        <p className="mt-1 text-sm text-slate-500">Default 20,000; one root DITAMAP references all topics.</p>
      </div>
      <div className="flex items-center space-x-2">
        <Switch
          id="bulk-dita-readme"
          checked={recipe.include_readme !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_readme: checked })}
        />
        <Label htmlFor="bulk-dita-readme">Include README.txt</Label>
      </div>
      <div className="flex items-center space-x-2">
        <Switch
          id="bulk-dita-pretty"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
        />
        <Label htmlFor="bulk-dita-pretty">Pretty-print XML</Label>
      </div>
      <div className="flex items-center space-x-2">
        <Switch
          id="bulk-dita-dtd-stubs"
          checked={stubsOn}
          onCheckedChange={(checked) => onChange({ ...recipe, include_local_dtd_stubs: checked })}
        />
        <Label htmlFor="bulk-dita-dtd-stubs">Include technicalContent DTD stubs (recommended)</Label>
      </div>
    </div>
  );
}
