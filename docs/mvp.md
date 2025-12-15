# 📘 Databento Pipeline - Guía de Implementación Detallada

## 🎯 Objetivo Final
Crear 3 scripts Python que descarguen, agreguen y validen datos OHLCV de Databento, con documentación completa para usuario no técnico.

**Timeline:** 1-2 días  
**Entrega:** Proton Drive  
**Comunicación:** WhatsApp para updates

---

## 📋 FASE 0: PREPARACIÓN (30 minutos)

### Paso 0.1: Crear Estructura del Proyecto
```bash
# En tu máquina local
mkdir databento-pipeline
cd databento-pipeline

# Crear estructura de carpetas
mkdir -p scripts
mkdir -p data/raw_1s
mkdir -p data/aggregated/15s
mkdir -p data/aggregated/30s
mkdir -p data/aggregated/1min
mkdir -p logs
mkdir -p tests

# Inicializar git (opcional pero recomendado)
git init
```

### Paso 0.2: Crear Archivo .gitignore
```bash
# .gitignore
data/
logs/
*.pyc
__pycache__/
.env
*.log
.DS_Store
*.csv
*.zip
.idea/
.vscode/
```

### Paso 0.3: Crear .env
```bash
# .env
DATABENTO_API_KEY=db-TU_API_KEY_AQUI
```

### Paso 0.4: Crear requirements.txt
```txt
# requirements.txt
pandas>=2.0.0
numpy>=1.24.0
python-dotenv>=1.0.0
databento>=0.36.0
requests>=2.31.0
```

### Paso 0.5: Instalar Dependencias
```bash
# Crear entorno virtual (recomendado)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# o
.\venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt
```

---

## 📋 FASE 1: TEST DE CONEXIÓN (15 minutos)

### Paso 1.1: Crear Script de Test
```python
# test_connection.py
import databento as db
import os
from dotenv import load_dotenv

def test_databento_connection():
    """Test básico de conexión a Databento API"""
    print("🔍 Testing Databento API connection...")
    
    # Cargar API key
    load_dotenv()
    api_key = os.getenv('DATABENTO_API_KEY')
    
    if not api_key:
        print("❌ ERROR: DATABENTO_API_KEY not found in .env")
        return False
    
    try:
        # Crear cliente
        client = db.Historical(api_key)
        print("✅ Databento client created successfully")
        
        # Test básico: obtener datasets disponibles
        datasets = client.metadata.list_datasets()
        print(f"✅ Available datasets: {len(datasets)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_databento_connection()
    if success:
        print("\n✅ Ready to proceed with development!")
    else:
        print("\n❌ Fix connection issues before continuing")
```

### Paso 1.2: Ejecutar Test
```bash
python test_connection.py
```

**Resultado esperado:**
```
🔍 Testing Databento API connection...
✅ Databento client created successfully
✅ Available datasets: X
✅ Ready to proceed with development!
```

---

## 📋 FASE 2: DOWNLOADER SCRIPT (3-4 horas)

### Paso 2.1: Crear Estructura Básica del Downloader
```python
# scripts/fetch_1s_bars.py
"""
Databento 1-Second OHLCV Downloader
Downloads monthly OHLCV data from Databento API
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import databento as db
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DatabentoDownloader:
    """Handles downloading 1-second OHLCV data from Databento"""
    
    def __init__(self, api_key):
        """Initialize Databento client"""
        self.client = db.Historical(api_key)
        logger.info("Databento client initialized")
    
    def download_month(self, symbol, year, month, output_dir, force=False):
        """
        Download 1-second OHLCV data for a specific month
        
        Args:
            symbol (str): Trading symbol (e.g., 'ES', 'SPY')
            year (int): Year (e.g., 2024)
            month (int): Month (1-12)
            output_dir (str): Output directory path
            force (bool): Force re-download if file exists
            
        Returns:
            bool: True if successful, False otherwise
        """
        # TODO: Implementar lógica de descarga
        pass
    
    def download_range(self, symbol, start_date, end_date, output_dir, force=False):
        """
        Download data for a date range (iterates month by month)
        
        Args:
            symbol (str): Trading symbol
            start_date (str): Start date (YYYY-MM-DD)
            end_date (str): End date (YYYY-MM-DD)
            output_dir (str): Output directory path
            force (bool): Force re-download existing files
            
        Returns:
            dict: Summary of downloads (success/failed/skipped)
        """
        # TODO: Implementar iteración mensual
        pass


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Download 1-second OHLCV data from Databento'
    )
    
    parser.add_argument(
        '--symbol',
        type=str,
        required=True,
        help='Trading symbol (e.g., ES, SPY, QQQ)'
    )
    
    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--output_dir',
        type=str,
        default='data/raw_1s',
        help='Output directory (default: data/raw_1s)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-download existing files'
    )
    
    return parser.parse_args()


def main():
    """Main execution function"""
    # Parse arguments
    args = parse_arguments()
    
    # Load API key
    load_dotenv()
    api_key = os.getenv('DATABENTO_API_KEY')
    
    if not api_key:
        logger.error("DATABENTO_API_KEY not found in environment")
        sys.exit(1)
    
    # Initialize downloader
    downloader = DatabentoDownloader(api_key)
    
    # Download data
    logger.info(f"Starting download: {args.symbol} from {args.start} to {args.end}")
    
    summary = downloader.download_range(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir,
        force=args.force
    )
    
    # Print summary
    logger.info("=" * 60)
    logger.info("DOWNLOAD SUMMARY")
    logger.info(f"Successfully downloaded: {summary.get('success', 0)}")
    logger.info(f"Skipped (already exists): {summary.get('skipped', 0)}")
    logger.info(f"Failed: {summary.get('failed', 0)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
```

### Paso 2.2: Implementar download_month()
```python
def download_month(self, symbol, year, month, output_dir, force=False):
    """Download 1-second OHLCV data for a specific month"""
    
    # Crear nombre de archivo
    filename = f"{symbol}_{year}_{month:02d}.csv"
    filepath = Path(output_dir) / symbol / filename
    
    # Check si ya existe
    if filepath.exists() and not force:
        logger.info(f"⏭️  Skipping {filename} (already exists)")
        return {'status': 'skipped', 'file': str(filepath)}
    
    # Crear directorio si no existe
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Calcular fechas del mes
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(seconds=1)
        
        logger.info(f"📥 Downloading {symbol} for {year}-{month:02d}...")
        
        # Hacer request a Databento
        # NOTA: Ajusta según la API real de Databento
        data = self.client.timeseries.get_range(
            dataset='GLBX.MDP3',  # Ajustar según tu dataset
            symbols=[symbol],
            schema='ohlcv-1s',
            start=start.isoformat(),
            end=end.isoformat(),
        )
        
        # Convertir a DataFrame
        df = data.to_df()
        
        if df.empty:
            logger.warning(f"⚠️  No data returned for {filename}")
            return {'status': 'failed', 'error': 'No data', 'file': str(filepath)}
        
        # Guardar CSV
        df.to_csv(filepath, index=True)
        logger.info(f"✅ Saved {filename} ({len(df)} rows)")
        
        return {'status': 'success', 'file': str(filepath), 'rows': len(df)}
        
    except Exception as e:
        logger.error(f"❌ Failed to download {filename}: {str(e)}")
        return {'status': 'failed', 'error': str(e), 'file': str(filepath)}
```

### Paso 2.3: Implementar download_range()
```python
def download_range(self, symbol, start_date, end_date, output_dir, force=False):
    """Download data for a date range (month by month)"""
    
    # Parse dates
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Initialize counters
    summary = {'success': 0, 'skipped': 0, 'failed': 0}
    
    # Iterate month by month
    current = start
    while current <= end:
        result = self.download_month(
            symbol=symbol,
            year=current.year,
            month=current.month,
            output_dir=output_dir,
            force=force
        )
        
        # Update counters
        summary[result['status']] += 1
        
        # Move to next month
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)
    
    return summary
```

### Paso 2.4: Test del Downloader
```bash
# Test con 1 mes de datos
python scripts/fetch_1s_bars.py \
    --symbol ES \
    --start 2024-01-01 \
    --end 2024-01-31 \
    --output_dir data/raw_1s

# Test de resume (debe skip el archivo existente)
python scripts/fetch_1s_bars.py \
    --symbol ES \
    --start 2024-01-01 \
    --end 2024-01-31 \
    --output_dir data/raw_1s

# Test de force re-download
python scripts/fetch_1s_bars.py \
    --symbol ES \
    --start 2024-01-01 \
    --end 2024-01-31 \
    --output_dir data/raw_1s \
    --force
```

---

## 📋 FASE 3: AGGREGATOR SCRIPT (3-4 horas)

### Paso 3.1: Crear Estructura del Aggregator
```python
# scripts/resample_bars.py
"""
OHLCV Aggregator - Resample 1-second bars to higher timeframes
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import pandas as pd
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/aggregator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OHLCVAggregator:
    """Resamples 1-second OHLCV data to higher timeframes"""
    
    # Map de timeframes legibles a pandas frequency
    TIMEFRAME_MAP = {
        '15s': '15S',
        '30s': '30S',
        '1min': '1T',
        '45s': '45S',  # Para futuras extensiones
    }
    
    def __init__(self):
        """Initialize aggregator"""
        logger.info("OHLCV Aggregator initialized")
    
    def resample_ohlcv(self, df, timeframe):
        """
        Resample OHLCV data to specified timeframe
        
        Args:
            df (pd.DataFrame): Input DataFrame with OHLCV data
            timeframe (str): Target timeframe (e.g., '15s', '30s', '1min')
            
        Returns:
            pd.DataFrame: Resampled OHLCV data
        """
        # TODO: Implementar lógica de resampling
        pass
    
    def process_file(self, input_file, output_dir, timeframes):
        """
        Process a single 1-second CSV file
        
        Args:
            input_file (str): Path to input CSV
            output_dir (str): Output directory
            timeframes (list): List of timeframes to generate
            
        Returns:
            dict: Processing results
        """
        # TODO: Implementar procesamiento de archivo
        pass
    
    def process_symbol(self, symbol, input_dir, output_dir, timeframes):
        """
        Process all files for a symbol
        
        Args:
            symbol (str): Trading symbol
            input_dir (str): Input directory with 1s data
            output_dir (str): Output directory
            timeframes (list): List of timeframes
            
        Returns:
            dict: Summary of processing
        """
        # TODO: Implementar procesamiento de símbolo
        pass


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Aggregate 1-second OHLCV to higher timeframes'
    )
    
    parser.add_argument(
        '--symbol',
        type=str,
        required=True,
        help='Trading symbol'
    )
    
    parser.add_argument(
        '--input_dir',
        type=str,
        default='data/raw_1s',
        help='Input directory with 1s data'
    )
    
    parser.add_argument(
        '--output_dir',
        type=str,
        default='data/aggregated',
        help='Output directory'
    )
    
    parser.add_argument(
        '--timeframes',
        type=str,
        default='15s,30s,1min',
        help='Comma-separated timeframes (default: 15s,30s,1min)'
    )
    
    return parser.parse_args()


def main():
    """Main execution"""
    args = parse_arguments()
    
    # Parse timeframes
    timeframes = [tf.strip() for tf in args.timeframes.split(',')]
    
    # Initialize aggregator
    aggregator = OHLCVAggregator()
    
    # Process symbol
    logger.info(f"Processing {args.symbol} for timeframes: {timeframes}")
    
    summary = aggregator.process_symbol(
        symbol=args.symbol,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        timeframes=timeframes
    )
    
    # Print summary
    logger.info("=" * 60)
    logger.info("AGGREGATION SUMMARY")
    logger.info(f"Files processed: {summary.get('processed', 0)}")
    logger.info(f"Timeframes generated: {summary.get('timeframes_created', 0)}")
    logger.info(f"Failed: {summary.get('failed', 0)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
```

### Paso 3.2: Implementar resample_ohlcv()
```python
def resample_ohlcv(self, df, timeframe):
    """Resample OHLCV data to specified timeframe"""
    
    # Validar que el timeframe esté soportado
    if timeframe not in self.TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    
    # Obtener frequency de pandas
    freq = self.TIMEFRAME_MAP[timeframe]
    
    try:
        # Asegurar que el índice sea datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        # Definir reglas de agregación OHLCV
        agg_rules = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # Resample
        resampled = df.resample(freq, label='left', closed='left').agg(agg_rules)
        
        # Eliminar filas con NaN (períodos sin datos)
        resampled = resampled.dropna()
        
        logger.debug(f"Resampled to {timeframe}: {len(df)} → {len(resampled)} rows")
        
        return resampled
        
    except Exception as e:
        logger.error(f"Error resampling to {timeframe}: {str(e)}")
        raise
```

### Paso 3.3: Implementar process_file()
```python
def process_file(self, input_file, output_dir, timeframes):
    """Process a single 1-second CSV file"""
    
    input_path = Path(input_file)
    
    if not input_path.exists():
        logger.error(f"File not found: {input_file}")
        return {'status': 'failed', 'error': 'File not found'}
    
    try:
        # Leer CSV
        logger.info(f"📖 Reading {input_path.name}...")
        df = pd.read_csv(input_file, index_col=0, parse_dates=True)
        
        # Validar columnas OHLCV
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            logger.error(f"Missing OHLCV columns in {input_path.name}")
            return {'status': 'failed', 'error': 'Missing columns'}
        
        results = []
        
        # Procesar cada timeframe
        for tf in timeframes:
            try:
                # Resample
                resampled = self.resample_ohlcv(df, tf)
                
                # Crear nombre de archivo output
                # Input: ES_2024_01.csv → Output: ES_2024_01_15s.csv
                base_name = input_path.stem  # ES_2024_01
                output_filename = f"{base_name}_{tf}.csv"
                
                # Crear directorio de output
                output_path = Path(output_dir) / tf / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Guardar
                resampled.to_csv(output_path, index=True)
                logger.info(f"✅ Saved {output_filename} ({len(resampled)} rows)")
                
                results.append({
                    'timeframe': tf,
                    'status': 'success',
                    'rows': len(resampled),
                    'file': str(output_path)
                })
                
            except Exception as e:
                logger.error(f"❌ Failed to process {tf}: {str(e)}")
                results.append({
                    'timeframe': tf,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return {'status': 'success', 'results': results}
        
    except Exception as e:
        logger.error(f"❌ Error processing {input_path.name}: {str(e)}")
        return {'status': 'failed', 'error': str(e)}
```

### Paso 3.4: Implementar process_symbol()
```python
def process_symbol(self, symbol, input_dir, output_dir, timeframes):
    """Process all files for a symbol"""
    
    # Encontrar todos los CSVs del símbolo
    symbol_dir = Path(input_dir) / symbol
    
    if not symbol_dir.exists():
        logger.error(f"Symbol directory not found: {symbol_dir}")
        return {'processed': 0, 'failed': 1, 'timeframes_created': 0}
    
    csv_files = sorted(symbol_dir.glob('*.csv'))
    
    if not csv_files:
        logger.warning(f"No CSV files found in {symbol_dir}")
        return {'processed': 0, 'failed': 0, 'timeframes_created': 0}
    
    logger.info(f"Found {len(csv_files)} files to process")
    
    # Counters
    processed = 0
    failed = 0
    timeframes_created = 0
    
    # Procesar cada archivo
    for csv_file in csv_files:
        result = self.process_file(
            input_file=str(csv_file),
            output_dir=output_dir,
            timeframes=timeframes
        )
        
        if result['status'] == 'success':
            processed += 1
            # Contar timeframes exitosos
            for r in result['results']:
                if r['status'] == 'success':
                    timeframes_created += 1
        else:
            failed += 1
    
    return {
        'processed': processed,
        'failed': failed,
        'timeframes_created': timeframes_created
    }
```

### Paso 3.5: Test del Aggregator
```bash
# Agregar el mes de prueba descargado anteriormente
python scripts/resample_bars.py \
    --symbol ES \
    --input_dir data/raw_1s \
    --output_dir data/aggregated \
    --timeframes 15s,30s,1min

# Verificar outputs
ls -lh data/aggregated/15s/
ls -lh data/aggregated/30s/
ls -lh data/aggregated/1min/
```

---

## 📋 FASE 4: VALIDATOR SCRIPT (2 horas)

### Paso 4.1: Crear Validator
```python
# scripts/validate_bars.py
"""
OHLCV Validator - Validate aggregated bars
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import pandas as pd
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/validator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OHLCVValidator:
    """Validates OHLCV data integrity"""
    
    def __init__(self):
        """Initialize validator"""
        self.errors = []
        self.warnings = []
    
    def check_duplicates(self, df, filename):
        """Check for duplicate timestamps"""
        duplicates = df.index.duplicated()
        if duplicates.any():
            count = duplicates.sum()
            msg = f"❌ {filename}: Found {count} duplicate timestamps"
            logger.error(msg)
            self.errors.append(msg)
            return False
        return True
    
    def check_timestamp_alignment(self, df, timeframe, filename):
        """Check if timestamps are aligned to timeframe boundaries"""
        # Convertir timeframe a segundos
        tf_seconds = {
            '15s': 15,
            '30s': 30,
            '1min': 60,
            '45s': 45
        }
        
        if timeframe not in tf_seconds:
            return True  # Skip check para timeframes no conocidos
        
        seconds = tf_seconds[timeframe]
        
        # Check que todos los timestamps sean múltiplos correctos
        misaligned = []
        for ts in df.index:
            total_seconds = ts.hour * 3600 + ts.minute * 60 + ts.second
            if total_seconds % seconds != 0:
                misaligned.append(ts)
        
        if misaligned:
            msg = f"⚠️  {filename}: {len(misaligned)} timestamps not aligned to {timeframe}"
            logger.warning(msg)
            self.warnings.append(msg)
            return False
        
        return True
    
    def check_ohlc_rules(self, df, filename):
        """Check OHLC logical rules"""
        errors_found = False
        
        # Rule 1: high >= open and high >= close
        high_violations = (df['high'] < df['open']) | (df['high'] < df['close'])
        if high_violations.any():
            count = high_violations.sum()
            msg = f"❌ {filename}: {count} rows where high < open or close"
            logger.error(msg)
            self.errors.append(msg)
            errors_found = True
        
        # Rule 2: low <= open and low <= close
        low_violations = (df['low'] > df['open']) | (df['low'] > df['close'])
        if low_violations.any():
            count = low_violations.sum()
            msg = f"❌ {filename}: {count} rows where low > open or close"
            logger.error(msg)
            self.errors.append(msg)
            errors_found = True
        
        # Rule 3: high >= low
        hl_violations = df['high'] < df['low']
        if hl_violations.any():
            count = hl_violations.sum()
            msg = f"❌ {filename}: {count} rows where high < low"
            logger.error(msg)
            self.errors.append(msg)
            errors_found = True
        
        return not errors_found
    
    def check_volume_sum(self, raw_file, agg_file, timeframe, filename):
        """Check if aggregated volume equals sum of raw volume"""
        # Este check es más complejo - requiere comparar con datos originales
        # Por simplicidad, lo dejamos como opcional/stub
        logger.debug(f"Volume sum check for {filename} - SKIPPED (requires raw data)")
        return True
    
    def validate_file(self, filepath, timeframe=None):
        """
        Validate a single OHLCV file
        
        Args:
            filepath (str): Path to CSV file
            timeframe (str): Timeframe of the data (for alignment check)
            
        Returns:
            bool: True if all checks pass
        """
        path = Path(filepath)
        filename = path.name
        
        try:
            # Leer archivo
            df = pd.read_csv(filepath, index_col=0, parse_dates=True)
            
            # Validar columnas
            required = ['open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required):
                msg = f"❌ {filename}: Missing OHLCV columns"
                logger.error(msg)
                self.errors.append(msg)
                return False
            
            # Run checks
            checks = [
                self.check_duplicates(df, filename),
                self.check_ohlc_rules(df, filename)
            ]
            
            if timeframe:
                checks.append(
                    self.check_timestamp_alignment(df, timeframe, filename)
                )
            
            # All checks passed?
            if all(checks):
                logger.info(f"✅ {filename}: All checks passed")
                return True
            else:
                return False
                
        except Exception as e:
            msg = f"❌ {filename}: Validation error - {str(e)}"
            logger.error(msg)
            self.errors.append(msg)
            return False
    
    def validate_directory(self, directory, timeframe=None):
        """Validate all CSV files in a directory"""
        dir_path = Path(directory)
        
        if not dir_path.exists():
            logger.error(f"Directory not found: {directory}")
            return False
        
        csv_files = list(dir_path.glob('*.csv'))
        
        if not csv_files:
            logger.warning(f"No CSV files found in {directory}")
            return True
        
        logger.info(f"Validating {len(csv_files)} files in {directory}")
        
        passed = 0
        failed = 0
        
        for csv_file in csv_files:
            if self.validate_file(str(csv_file), timeframe):
                passed += 1
            else:
                failed += 1
        
        logger.info(f"Validation complete: {passed} passed, {failed} failed")
        
        return failed == 0
    
    def write_report(self, output_file='logs/validation_report.txt'):
        """Write validation report to file"""
        with open(output_file, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("OHLCV VALIDATION REPORT\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"ERRORS FOUND: {len(self.errors)}\n")
            for error in self.errors:
                f.write(f"  - {error}\n")
            
            f.write(f"\nWARNINGS: {len(self.warnings)}\n")
            for warning in self.warnings:
                f.write(f"  - {warning}\n")
            
            f.write("\n" + "=" * 60 + "\n")
        
        logger.info(f"Report written to {output_file}")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Validate OHLCV data integrity'
    )
    
    parser.add_argument(
        '--input_dir',
        type=str,
        required=True,
        help='Directory with CSV files to validate'
    )
    
    parser.add_argument(
        '--timeframe',
        type=str,
        help='Timeframe of the data (for alignment check)'
    )
    
    parser.add_argument(
        '--report',
        type=str,
        default='logs/validation_report.txt',
        help='Output report file'
    )
    
    return parser.parse_args()


def main():
    """Main execution"""
    args = parse_arguments()
    
    # Initialize validator
    validator = OHLCVValidator()
    
    # Validate
    logger.info(f"Starting validation of {args.input_dir}")
    success = validator.validate_directory(args.input_dir, args.timeframe)
    
    # Write report
    validator.write_report(args.report)
    
    # Exit code
    if success:
        logger.info("✅ All validations passed!")
        sys.exit(0)
    else:
        logger.error("❌ Validation failed - check report for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Paso 4.2: Test del Validator
```bash
# Validar datos agregados de 15s
python scripts/validate_bars.py \
    --input_dir data/aggregated/15s \
    --timeframe 15s \
    --report logs/validation_15s.txt

# Validar datos agregados de 30s
python scripts/validate_bars.py \
    --input_dir data/aggregated/30s \
    --timeframe 30s \
    --report logs/validation_30s.txt

# Validar datos agregados de 1min
python scripts/validate_bars.py \
    --input_dir data/aggregated/1min \
    --timeframe 1min \
    --report logs/validation_1min.txt
```

---

## 📋 FASE 5: DOCUMENTACIÓN (2 horas)

### Paso 5.1: Crear README.md Completo
```markdown
# Databento OHLCV Pipeline

Professional toolset for downloading and aggregating 1-second OHLCV data from Databento.

## 📋 Table of Contents
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Download 1-Second Data](#download-1-second-data)
  - [Aggregate to Higher Timeframes](#aggregate-to-higher-timeframes)
  - [Validate Data](#validate-data)
- [Directory Structure](#directory-structure)
- [Adding New Timeframes](#adding-new-timeframes)
- [Troubleshooting](#troubleshooting)

---

## 🔧 Requirements

- **Python**: 3.9 or higher
- **Operating System**: Linux (tested on Ubuntu 20.04+)
- **Databento Account**: Active account with API access

---

## 📦 Installation

### Step 1: Clone or Download the Project
```bash
# If using git
git clone <repository-url>
cd databento-pipeline

# Or extract from zip
unzip databento-pipeline.zip
cd databento-pipeline
```

### Step 2: Create Virtual Environment (Recommended)
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Verify Installation
```bash
python -c "import databento; print('✅ Databento installed successfully')"
```

---

## ⚙️ Configuration

### Set Databento API Key

**Option 1: Environment Variable (Recommended)**
```bash
export DATABENTO_API_KEY='your-api-key-here'
```

**Option 2: .env File**
```bash
# Create .env file in project root
echo "DATABENTO_API_KEY=your-api-key-here" > .env
```

**Option 3: Direct in Shell**
```bash
# For one-time use
DATABENTO_API_KEY='your-key' python scripts/fetch_1s_bars.py ...
```

---

## 🚀 Usage

### Download 1-Second Data

**Basic Usage:**
```bash
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --start 2021-01-01 \
  --end 2021-12-31 \
  --output_dir data/raw_1s
```

**Parameters:**
- `--symbol`: Trading symbol (e.g., ES, SPY, QQQ, NQ, GC)
- `--start`: Start date (YYYY-MM-DD)
- `--end`: End date (YYYY-MM-DD)
- `--output_dir`: Output directory (default: data/raw_1s)
- `--force`: Force re-download existing files (optional)

**Examples:**

Download SPY for 2024:
```bash
python scripts/fetch_1s_bars.py \
  --symbol SPY \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --output_dir data/raw_1s
```

Download multiple months with resume capability:
```bash
# First run - downloads 6 months
python scripts/fetch_1s_bars.py \
  --symbol QQQ \
  --start 2023-01-01 \
  --end 2023-06-30 \
  --output_dir data/raw_1s

# Second run - downloads remaining 6 months (skips already downloaded)
python scripts/fetch_1s_bars.py \
  --symbol QQQ \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --output_dir data/raw_1s
```

Force re-download (overwrite existing files):
```bash
python scripts/fetch_1s_bars.py \
  --symbol ES \
  --start 2024-01-01 \
  --end 2024-01-31 \
  --output_dir data/raw_1s \
  --force
```

---

### Aggregate to Higher Timeframes

**Basic Usage:**
```bash
python scripts/resample_bars.py \
  --symbol ES \
  --input_dir data/raw_1s \
  --output_dir data/aggregated \
  --timeframes 15s,30s,1min
```

**Parameters:**
- `--symbol`: Trading symbol
- `--input_dir`: Directory with 1-second CSV files (default: data/raw_1s)
- `--output_dir`: Output directory (default: data/aggregated)
- `--timeframes`: Comma-separated timeframes (default: 15s,30s,1min)

**Examples:**

Aggregate SPY to default timeframes:
```bash
python scripts/resample_bars.py \
  --symbol SPY \
  --input_dir data/raw_1s \
  --output_dir data/aggregated
```

Generate only specific timeframes:
```bash
python scripts/resample_bars.py \
  --symbol ES \
  --timeframes 15s,1min
```

---

### Validate Data

**Basic Usage:**
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s \
  --report logs/validation_15s.txt
```

**Parameters:**
- `--input_dir`: Directory with CSV files to validate
- `--timeframe`: Timeframe for alignment check (optional)
- `--report`: Output report file (default: logs/validation_report.txt)

**Examples:**

Validate all 15-second bars:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/15s \
  --timeframe 15s
```

Validate 1-minute bars:
```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/1min \
  --timeframe 1min
```

---

## 📁 Directory Structure

```
databento-pipeline/
├── scripts/
│   ├── fetch_1s_bars.py      # Download 1-second data
│   ├── resample_bars.py       # Aggregate to higher timeframes
│   └── validate_bars.py       # Validate data integrity
│
├── data/
│   ├── raw_1s/                # Downloaded 1-second data
│   │   ├── ES/
│   │   │   ├── ES_2021_01.csv
│   │   │   ├── ES_2021_02.csv
│   │   │   └── ...
│   │   ├── SPY/
│   │   └── QQQ/
│   │
│   └── aggregated/            # Aggregated data
│       ├── 15s/
│       │   ├── ES_2021_01_15s.csv
│       │   └── ...
│       ├── 30s/
│       └── 1min/
│
├── logs/                      # Log files
│   ├── downloader.log
│   ├── aggregator.log
│   ├── validator.log
│   └── validation_report.txt
│
├── requirements.txt           # Python dependencies
├── .env                       # API key (create this)
└── README.md                  # This file
```

---

## 🔧 Adding New Timeframes

Want to add a new timeframe like 45 seconds or 2 minutes?

### Step 1: Update the Timeframe Map

Edit `scripts/resample_bars.py` at line ~30:

```python
TIMEFRAME_MAP = {
    '15s': '15S',
    '30s': '30S',
    '1min': '1T',
    '45s': '45S',    # ← Add this line
    '2min': '2T',    # ← Or this
}
```

### Step 2: Run Aggregation

```bash
python scripts/resample_bars.py \
  --symbol ES \
  --timeframes 45s
```

### Step 3: Validate (Optional)

```bash
python scripts/validate_bars.py \
  --input_dir data/aggregated/45s \
  --timeframe 45s
```

**That's it!** The new timeframe is now available.

---

## 🔍 Troubleshooting

### Error: "DATABENTO_API_KEY not found"

**Problem:** API key not set in environment.

**Solution:**
```bash
# Check if key is set
echo $DATABENTO_API_KEY

# If empty, set it
export DATABENTO_API_KEY='your-key-here'

# Or use .env file
echo "DATABENTO_API_KEY=your-key" > .env
```

---

### Error: "No module named 'databento'"

**Problem:** Dependencies not installed.

**Solution:**
```bash
pip install -r requirements.txt
```

---

### Warning: "No data returned for month"

**Problem:** Databento has no data for that symbol/date range.

**Causes:**
- Symbol not available for that date
- Wrong dataset selected
- Market was closed (holidays)

**Solution:**
- Verify symbol is correct
- Check Databento documentation for data availability
- Try a different date range

---

### Error: "Permission denied" when writing files

**Problem:** No write permissions for output directory.

**Solution:**
```bash
# Create directories with correct permissions
mkdir -p data/raw_1s data/aggregated logs
chmod 755 data data/raw_1s data/aggregated logs

# Or run with sudo (not recommended for production)
sudo python scripts/fetch_1s_bars.py ...
```

---

### Files are not being skipped (resume not working)

**Problem:** Resume logic not detecting existing files.

**Possible causes:**
- Files in wrong directory
- Filename format mismatch

**Solution:**
```bash
# Check existing files
ls -lh data/raw_1s/ES/

# Expected format: ES_2024_01.csv
# If files are named differently, they won't be detected

# Force re-download if needed
python scripts/fetch_1s_bars.py ... --force
```

---

### Aggregated data looks wrong

**Problem:** OHLCV aggregation producing unexpected results.

**Solution:**
1. Check input data:
```bash
head -20 data/raw_1s/ES/ES_2024_01.csv
```

2. Run validation:
```bash
python scripts/validate_bars.py --input_dir data/aggregated/15s --timeframe 15s
```

3. Check logs:
```bash
cat logs/aggregator.log
cat logs/validation_report.txt
```

---

### Common Pandas Issues

**Problem:** "ValueError: time data does not match format"

**Solution:** Ensure timestamp column is in ISO format (YYYY-MM-DD HH:MM:SS)

**Problem:** "Memory error" when processing large files

**Solution:** Process files in smaller batches or use chunking:
```python
# In resample_bars.py, modify read_csv:
df = pd.read_csv(file, chunksize=100000)
```

---

## ⏱️ Expected Runtime Notes

**Download times** (approximate, per symbol per month):
- 1-second data: 30-60 seconds (depending on network and API)
- For 60 months: ~30-60 minutes total per symbol

**Aggregation times** (per month):
- 15s bars: 2-5 seconds
- 30s bars: 2-5 seconds
- 1min bars: 2-5 seconds
- For 60 months: ~5-10 minutes total per symbol

**Validation times** (per timeframe):
- ~1-2 seconds per file
- For 60 files: ~2-3 minutes

**Total pipeline** (download + aggregate + validate):
- Single symbol, 60 months: ~45-75 minutes

---

## 📞 Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review this troubleshooting section
3. Contact project maintainer

---

## 📄 License

[Specify license here]

---

**Version:** 1.0  
**Last Updated:** [Current Date]
```

### Paso 5.2: Crear .env.example
```bash
# .env.example
DATABENTO_API_KEY=your-api-key-here
```

### Paso 5.3: Agregar Comentarios al Código

Revisa cada script y agrega comentarios claros:

```python
# Ejemplo de buenos comentarios
def download_month(self, symbol, year, month, output_dir, force=False):
    """
    Download 1-second OHLCV data for a specific month.
    
    This function:
    1. Checks if the file already exists (resume-safe)
    2. Calls Databento API for the specified month
    3. Converts response to DataFrame
    4. Saves as CSV
    
    Args:
        symbol (str): Trading symbol (e.g., 'ES', 'SPY')
        year (int): Year (e.g., 2024)
        month (int): Month (1-12)
        output_dir (str): Output directory path
        force (bool): Force re-download if file exists
        
    Returns:
        dict: Result with status, file path, and row count
        
    Example:
        >>> downloader.download_month('ES', 2024, 1, 'data/raw_1s')
        {'status': 'success', 'file': 'data/raw_1s/ES/ES_2024_01.csv', 'rows': 50000}
    """
    # Implementation...
```

---

## 📋 FASE 6: TESTING COMPLETO (1-2 horas)

### Paso 6.1: Script de Testing Automatizado
```python
# test_pipeline.py
"""
Test completo del pipeline
"""

import os
import subprocess
import sys
from pathlib import Path

def run_command(cmd):
    """Run shell command and return status"""
    print(f"\n🔧 Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0

def test_pipeline():
    """Test completo del pipeline"""
    
    print("=" * 60)
    print("TESTING DATABENTO PIPELINE")
    print("=" * 60)
    
    # Test 1: Download
    print("\n📥 TEST 1: Download 1-second data")
    cmd = """
    python scripts/fetch_1s_bars.py \
        --symbol ES \
        --start 2024-01-01 \
        --end 2024-02-28 \
        --output_dir data/raw_1s
    """
    if not run_command(cmd):
        print("❌ Download test failed")
        return False
    
    # Test 2: Aggregate
    print("\n🔄 TEST 2: Aggregate to higher timeframes")
    cmd = """
    python scripts/resample_bars.py \
        --symbol ES \
        --input_dir data/raw_1s \
        --output_dir data/aggregated \
        --timeframes 15s,30s,1min
    """
    if not run_command(cmd):
        print("❌ Aggregation test failed")
        return False
    
    # Test 3: Validate
    print("\n✅ TEST 3: Validate aggregated data")
    for tf in ['15s', '30s', '1min']:
        cmd = f"""
        python scripts/validate_bars.py \
            --input_dir data/aggregated/{tf} \
            --timeframe {tf} \
            --report logs/validation_{tf}.txt
        """
        if not run_command(cmd):
            print(f"❌ Validation test failed for {tf}")
            return False
    
    # Test 4: Resume capability
    print("\n🔁 TEST 4: Test resume capability")
    cmd = """
    python scripts/fetch_1s_bars.py \
        --symbol ES \
        --start 2024-01-01 \
        --end 2024-02-28 \
        --output_dir data/raw_1s
    """
    if not run_command(cmd):
        print("❌ Resume test failed")
        return False
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_pipeline()
    sys.exit(0 if success else 1)
```

### Paso 6.2: Ejecutar Tests
```bash
python test_pipeline.py
```

---

## 📋 FASE 7: DELIVERY (1 hora)

### Paso 7.1: Checklist Pre-Delivery

```bash
# 1. Verificar que todos los scripts funcionen
python scripts/fetch_1s_bars.py --help
python scripts/resample_bars.py --help
python scripts/validate_bars.py --help

# 2. Verificar README
cat README.md

# 3. Limpiar archivos temporales
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -delete
rm -rf .pytest_cache

# 4. Verificar estructura
tree -L 3
```

### Paso 7.2: Crear Package para Entrega

```bash
# Crear archivo de entrega
cd ..
zip -r databento-pipeline.zip databento-pipeline \
    -x "databento-pipeline/data/*" \
    -x "databento-pipeline/logs/*" \
    -x "databento-pipeline/.git/*" \
    -x "databento-pipeline/venv/*" \
    -x "databento-pipeline/.env"

# Verificar contenido
unzip -l databento-pipeline.zip
```

### Paso 7.3: Upload a Proton Drive

1. Ve a Proton Drive
2. Navega al folder compartido
3. Upload `databento-pipeline.zip`
4. Verifica que se subió correctamente

### Paso 7.4: Mensaje de Entrega en WhatsApp

```
Hi JK and Pete,

✅ MVP is complete and uploaded to Proton Drive!

📦 Deliverables:
• fetch_1s_bars.py - Downloads 1s OHLCV with resume capability
• resample_bars.py - Aggregates to 15s/30s/1min (easily extensible)
• validate_bars.py - Data integrity checks
• Comprehensive README with examples and troubleshooting
• All tested with ES for Jan-Feb 2024

🎯 Key Features:
• Resume-safe downloads (skips existing files)
• Direct aggregation from 1s to each timeframe
• Timestamp alignment validation
• OHLC rule checking
• Full logging for debugging

📖 README includes:
• Installation steps
• CLI examples for all operations
• How to add new timeframes (e.g., 45s)
• Troubleshooting common issues
• Expected runtime estimates

Ready for your review. Let me know if you need any adjustments or have questions!
```

---

## 📊 CHECKLIST FINAL COMPLETO

```
SCRIPTS
[✓] fetch_1s_bars.py
    [✓] CLI arguments working
    [✓] Month-by-month iteration
    [✓] Resume-safe logic
    [✓] --force flag
    [✓] Logging
    [✓] Error handling
    
[✓] resample_bars.py
    [✓] Read 1s CSVs
    [✓] Resample to 15s/30s/1min
    [✓] Correct OHLCV rules
    [✓] Organized output
    [✓] Logging
    
[✓] validate_bars.py
    [✓] Check duplicates
    [✓] Check timestamp alignment
    [✓] Check OHLC rules
    [✓] Write report
    [✓] Logging

DOCUMENTATION
[✓] README.md complete
[✓] requirements.txt
[✓] .env.example
[✓] Code comments
[✓] CLI help texts

TESTING
[✓] Tested download
[✓] Tested aggregation
[✓] Tested validation
[✓] Tested resume logic
[✓] Tested --force flag
[✓] All timeframes working

DELIVERY
[✓] Code cleaned
[✓] Package created
[✓] Uploaded to Proton Drive
[✓] Message sent to client
```

---

## 🚨 NOTAS IMPORTANTES

### Sobre el API de Databento

**CRÍTICO:** La implementación exacta del download depende de la API real de Databento. Necesitas:

1. **Leer la documentación oficial:**
   - https://docs.databento.com/
   - Buscar ejemplos de código Python
   - Entender el schema 'ohlcv-1s'

2. **Posibles ajustes necesarios:**
   ```python
   # El código en download_month() puede necesitar ajustes:
   data = self.client.timeseries.get_range(
       dataset='GLBX.MDP3',  # ← Verificar dataset correcto
       symbols=[symbol],
       schema='ohlcv-1s',    # ← Verificar schema correcto
       start=start.isoformat(),
       end=end.isoformat(),
   )
   ```

3. **Test temprano:** Haz un test de API ANTES de escribir todo el código.

---

## ⏰ TIMELINE REALISTA

| Fase | Tiempo | Status |
|------|--------|--------|
| Fase 0: Setup | 30 min | ⏳ |
| Fase 1: Test conexión | 15 min | ⏳ |
| Fase 2: Downloader | 3-4 hrs | ⏳ |
| Fase 3: Aggregator | 3-4 hrs | ⏳ |
| Fase 4: Validator | 2 hrs | ⏳ |
| Fase 5: Docs | 2 hrs | ⏳ |
| Fase 6: Testing | 1-2 hrs | ⏳ |
| Fase 7: Delivery | 1 hr | ⏳ |
| **TOTAL** | **14-18 hrs** | |

**Distribución sugerida:**
- Día 1 (hoy): Fases 0-3 (8 horas)
- Día 2 (mañana): Fases 4-7 (6-8 horas)

---

¿Listo para empezar? **Comienza con Fase 0 y avísame cuando termines cada fase para ajustar si es necesario!**