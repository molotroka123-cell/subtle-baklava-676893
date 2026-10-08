# ТЗ: обучение LoRA персонажа на RunPod (RTX 6000 Ada)

Статус: ПОДГОТОВЛЕНО, НЕ ЗАПУСКАТЬ без команды Тимура.
Назначение: за ~1 час на арендованной GPU обучить LoRA персонажа (20+ референсов),
забрать файл и генерить локально на ПК. Потом — «за секунду» по этому документу.

## Железо

- GPU: `NVIDIA RTX 6000 Ada Generation` (48 ГБ VRAM), `gpuTypeId: "NVIDIA RTX 6000 Ada Generation"`
- Проверка 2026-10-08: тип доступен в RunPod API; ориентир цены — A40 48 ГБ стоит $0.35/час
  (6000 Ada дороже, смотреть актуальную цену в момент запуска через `runpod.py gpus`)
- Смета: ~1 час аренды ≈ $1–2

## Шаг 0. Датасет (делается заранее, локально)

- 20+ фото персонажа, 1024px, разные ракурсы/эмоции/свет, ≥1 в полный рост
- Лежат в `C:\Users\asd\Bossman\higgsfield\refs\` (подготовить до аренды — время пода тикает)
- Имя триггера LoRA: `sks_persona` (пример)

## Шаг 1. Запуск пода (только по команде «арендуй»)

```bash
python3 ~/workspace/skills/runpod/bin/runpod.py deploy \
  --gpu-type "NVIDIA RTX 6000 Ada Generation" \
  --name bossman-lora-train \
  --image "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04" \
  --disk 50
```

SSH-доступ: взять IP/порт из `runpod.py pods`, ключ — из RunPod console.

## Шаг 2. Обучение (на поде)

```bash
# на поде, /workspace
git clone https://github.com/kohya-ss/sd-scripts && cd sd-scripts
pip install -r requirements.txt
# датасет: /workspace/data/<trigger>/img/*.jpg + текстовые подписи
accelerate launch sdxl_train_network.py \
  --pretrained_model_name_or_path="/workspace/epicrealismXL_pureFix.safetensors" \
  --train_data_dir="/workspace/data/sks_persona" \
  --output_dir="/workspace/out" --output_name="sks_persona_lora" \
  --network_module="networks.lora" --network_dim=16 --network_alpha=8 \
  --learning_rate=1e-4 --lr_scheduler="cosine" \
  --max_train_epochs=10 --train_batch_size=1 \
  --optimizer_type="adamw8bit" --mixed_precision="bf16" \
  --resolution="1024,1024" --seed=42
```

Ориентир: 30–40 минут на 20 фото.

## Шаг 3. Забрать результат

- Файл: `/workspace/out/sks_persona_lora.safetensors` (~200–400 МБ)
- Скачать на ПК: `C:\Users\asd\Bossman\models\media\lora\`
- Проверить: файл открывается, размер > 50 МБ

## Шаг 4. Остановить под (сразу!)

```bash
python3 ~/workspace/skills/runpod/bin/runpod.py stop <POD_ID>
```

Проверить `runpod.py pods` — под должен исчезнуть из активных.

## Шаг 5. Локальный инференс (ПК, бесплатно)

```bash
sd-cli.exe -m epicrealismXL_pureFix.safetensors --lora sks_persona_lora.safetensors \
  -p "photo of sks_persona, ..." --steps 20 ...
```

## Чеклист «за секунду»

1. Датасет готов (20+ фото) → 2. `deploy` → 3. обучение (~40 мин) →
   4. скачать LoRA → 5. `stop` → 6. генерить локально

## Связанные документы

- Навык: `~/workspace/skills/runpod/` (CLI `bin/runpod.py`)
- Генерация через Higgsfield — только для НЕ-explicit контента (модерация);
  explicit — локально своими uncensored-моделями.
